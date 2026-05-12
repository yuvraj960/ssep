package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"math"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

var (
	rdb        *redis.Client
	logger     = slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	graph      *VenueGraph
	venueID    string
	redisAddr  string
	graphMutex sync.RWMutex
)

type Zone struct {
	ID        string  `json:"zone_id"`
	Name      string  `json:"name"`
	Type      string  `json:"type"`
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
}

type Edge struct {
	From        string  `json:"from_zone"`
	To          string  `json:"to_zone"`
	BaseWeight  float64 `json:"base_weight_seconds"`
	PassageType string  `json:"passage_type"`
}

type VenueGraph struct {
	Zones map[string]Zone `json:"zones"`
	Edges []Edge          `json:"edges"`
	adj   map[string][]adjEntry
}

type adjEntry struct {
	To          string
	BaseWeight  float64
	PassageType string
}

type RouteStep struct {
	ZoneID      string  `json:"zone_id"`
	ZoneName    string  `json:"zone_name"`
	PassageType string  `json:"passage_type"`
	EstSeconds  float64 `json:"estimated_seconds"`
	Congestion  float64 `json:"congestion"`
}

type RouteResponse struct {
	RouteID    string      `json:"route_id"`
	VenueID    string      `json:"venue_id"`
	From       string      `json:"from_zone"`
	To         string      `json:"to_zone"`
	Steps      []RouteStep `json:"steps"`
	TotalTime  float64     `json:"total_estimated_seconds"`
	Distance   int         `json:"step_count"`
	ComputedAt string      `json:"computed_at"`
}

type CongestionUpdate struct {
	ZoneID   string  `json:"zone_id"`
	Density  float64 `json:"density"`
}

type NavigationRequest struct {
	FromZone string `json:"from_zone"`
	ToZone   string `json:"to_zone"`
	AvoidZones []string `json:"avoid_zones,omitempty"`
}

type HealthResponse struct {
	Status       string `json:"status"`
	Service      string `json:"service"`
	ZonesLoaded  int    `json:"zones_loaded"`
	EdgesLoaded  int    `json:"edges_loaded"`
}

func loadVenueGraph(path string) (*VenueGraph, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading venue graph: %w", err)
	}
	var g VenueGraph
	if err := json.Unmarshal(data, &g); err != nil {
		return nil, fmt.Errorf("parsing venue graph: %w", err)
	}
	g.adj = make(map[string][]adjEntry)
	for _, e := range g.Edges {
		g.adj[e.From] = append(g.adj[e.From], adjEntry{
			To:          e.To,
			BaseWeight:  e.BaseWeight,
			PassageType: e.PassageType,
		})
		g.adj[e.To] = append(g.adj[e.To], adjEntry{
			To:          e.From,
			BaseWeight:  e.BaseWeight,
			PassageType: e.PassageType,
		})
	}
	return &g, nil
}

func getCongestionWeight(ctx context.Context, zoneID string, baseWeight float64) float64 {
	key := fmt.Sprintf("density:%s:%s", venueID, zoneID)
	val, err := rdb.Get(ctx, key).Result()
	if err != nil {
		return baseWeight
	}
	var data map[string]interface{}
	if err := json.Unmarshal([]byte(val), &data); err != nil {
		return baseWeight
	}
	if density, ok := data["density"].(float64); ok {
		multiplier := 1.0 + density*3.0
		if density >= 0.85 {
			multiplier = 5.0
		} else if density >= 0.65 {
			multiplier = 3.0
		}
		return baseWeight * multiplier
	}
	return baseWeight
}

func dijkstra(ctx context.Context, g *VenueGraph, start, end string, avoid map[string]bool) ([]RouteStep, float64) {
	graphMutex.RLock()
	defer graphMutex.RUnlock()

	dist := make(map[string]float64)
	prev := make(map[string]string)
	visited := make(map[string]bool)
	congestion := make(map[string]float64)

	for zID := range g.Zones {
		dist[zID] = math.Inf(1)
	}
	dist[start] = 0

	type node struct {
		id   string
		dist float64
	}

	pq := []node{{id: start, dist: 0}}

	for len(pq) > 0 {
		minIdx := 0
		for i := 1; i < len(pq); i++ {
			if pq[i].dist < pq[minIdx].dist {
				minIdx = i
			}
		}
		curr := pq[minIdx]
		pq = append(pq[:minIdx], pq[minIdx+1:]...)

		if visited[curr.id] {
			continue
		}
		visited[curr.id] = true

		if curr.id == end {
			break
		}

		for _, edge := range g.adj[curr.id] {
			if avoid[edge.To] || visited[edge.To] {
				continue
			}
			weight := getCongestionWeight(ctx, edge.To, edge.BaseWeight)
			newDist := dist[curr.id] + weight
			if newDist < dist[edge.To] {
				dist[edge.To] = newDist
				prev[edge.To] = curr.id
				pq = append(pq, node{id: edge.To, dist: newDist})
			}
		}
	}

	if dist[end] == math.Inf(1) {
		return nil, -1
	}

	var steps []RouteStep
	curr := end
	for curr != start {
		p := prev[curr]
		edge := findEdge(g, p, curr)
		zone := g.Zones[curr]
		steps = append([]RouteStep{{
			ZoneID:      curr,
			ZoneName:    zone.Name,
			PassageType: edge.PassageType,
			EstSeconds:  dist[curr] - dist[p],
			Congestion:  getCongestionFromCache(ctx, curr),
		}}, steps...)
		curr = p
	}

	return steps, dist[end]
}

func findEdge(g *VenueGraph, from, to string) adjEntry {
	for _, e := range g.adj[from] {
		if e.To == to {
			return e
		}
	}
	return adjEntry{BaseWeight: 30, PassageType: "corridor"}
}

func getCongestionFromCache(ctx context.Context, zoneID string) float64 {
	key := fmt.Sprintf("density:%s:%s", venueID, zoneID)
	val, err := rdb.Get(ctx, key).Result()
	if err != nil {
		return 0
	}
	var data map[string]interface{}
	if err := json.Unmarshal([]byte(val), &data); err != nil {
		return 0
	}
	if d, ok := data["density"].(float64); ok {
		return d
	}
	return 0
}

func navigationHandler(w http.ResponseWriter, r *http.Request) {
	var req NavigationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}

	graphMutex.RLock()
	if _, ok := graph.Zones[req.FromZone]; !ok {
		graphMutex.RUnlock()
		http.Error(w, "from_zone not found", http.StatusNotFound)
		return
	}
	if _, ok := graph.Zones[req.ToZone]; !ok {
		graphMutex.RUnlock()
		http.Error(w, "to_zone not found", http.StatusNotFound)
		return
	}
	graphMutex.RUnlock()

	avoid := make(map[string]bool)
	for _, z := range req.AvoidZones {
		avoid[z] = true
	}

	steps, totalSec := dijkstra(r.Context(), graph, req.FromZone, req.ToZone, avoid)
	if steps == nil {
		http.Error(w, "no route found", http.StatusNotFound)
		return
	}

	resp := RouteResponse{
		RouteID:    uuid.New.String(),
		VenueID:    venueID,
		From:       req.FromZone,
		To:         req.ToZone,
		Steps:      steps,
		TotalTime:  totalSec,
		Distance:   len(steps),
		ComputedAt: time.Now().UTC().Format(time.RFC3339),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func congestionUpdateHandler(w http.ResponseWriter, r *http.Request) {
	var updates []CongestionUpdate
	if err := json.NewDecoder(r.Body).Decode(&updates); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}

	graphMutex.Lock()
	for _, u := range updates {
		if zone, ok := graph.Zones[u.ZoneID]; ok {
			_ = zone
			key := fmt.Sprintf("density:%s:%s", venueID, u.ZoneID)
			data := map[string]interface{}{
				"zone_id":   u.ZoneID,
				"density":   u.Density,
			}
			val, _ := json.Marshal(data)
			rdb.Set(r.Context(), key, string(val), 5*time.Minute)
		}
	}
	graphMutex.Unlock()

	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":       "accepted",
		"updates_count": len(updates),
	})
}

func zonesHandler(w http.ResponseWriter, r *http.Request) {
	graphMutex.RLock()
	defer graphMutex.RUnlock()

	zones := make([]Zone, 0, len(graph.Zones))
	for _, z := range graph.Zones {
		zones = append(zones, z)
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"venue_id": venueID,
		"zones":    zones,
		"count":    len(zones),
	})
}

func bestGateHandler(w http.ResponseWriter, r *http.Request) {
	fromZone := r.URL.Query().Get("from")
	if fromZone == "" {
		fromZone = "parking-main"
	}

	graphMutex.RLock()
	gates := []string{}
	for _, z := range graph.Zones {
		if z.Type == "gate" {
			gates = append(gates, z.ID)
		}
	}
	graphMutex.RUnlock()

	type gateResult struct {
		GateID    string  `json:"gate_id"`
		GateName  string  `json:"gate_name"`
		WaitTime  float64 `json:"estimated_seconds"`
		Congestion float64 `json:"congestion"`
	}

	results := []gateResult{}
	for _, gate := range gates {
		_, totalSec := dijkstra(r.Context(), graph, fromZone, gate, nil)
		cong := getCongestionFromCache(r.Context(), gate)
		name := ""
		if z, ok := graph.Zones[gate]; ok {
			name = z.Name
		}
		results = append(results, gateResult{
			GateID:    gate,
			GateName:  name,
			WaitTime:  totalSec,
			Congestion: cong,
		})
	}

	for i := 0; i < len(results); i++ {
		for j := i + 1; j < len(results); j++ {
			scoreI := results[i].WaitTime * (1 + results[i].Congestion*2)
			scoreJ := results[j].WaitTime * (1 + results[j].Congestion*2)
			if scoreJ < scoreI {
				results[i], results[j] = results[j], results[i]
			}
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"venue_id":   venueID,
		"from_zone":  fromZone,
		"best_gate":  results,
		"computed_at": time.Now().UTC().Format(time.RFC3339),
	})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	graphMutex.RLock()
	zones := len(graph.Zones)
	edges := len(graph.Edges)
	graphMutex.RUnlock()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(HealthResponse{
		Status:      "healthy",
		Service:     "navigation",
		ZonesLoaded: zones,
		EdgesLoaded: edges,
	})
}

func main() {
	venueID = getEnv("VENUE_ID", "stadium-001")
	redisAddr = getEnv("REDIS_HOST", "localhost:6379")

	parts := splitHostPort(redisAddr)
	rdb = redis.NewClient(&redis.Options{
		Addr:     fmt.Sprintf("%s:%d", parts[0], parts[1]),
		Password: "",
		DB:       0,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		logger.Warn("redis_connection_failed", "error", err.Error())
	}

	graphPath := getEnv("VENUE_GRAPH_PATH", "/app/venue_graph.json")
	var err error
	graph, err = loadVenueGraph(graphPath)
	if err != nil {
		logger.Error("failed_to_load_venue_graph", "error", err.Error())
		os.Exit(1)
	}
	logger.Info("navigation_service_started", "venue_id", venueID, "zones", len(graph.Zones), "edges", len(graph.Edges))

	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(30 * time.Second))

	r.Post("/api/v1/navigate", navigationHandler)
	r.Post("/api/v1/congestion/update", congestionUpdateHandler)
	r.Get("/api/v1/zones", zonesHandler)
	r.Get("/api/v1/best-gate", bestGateHandler)
	r.Get("/health", healthHandler)

	port := getEnv("PORT", "8082")
	logger.Info("listening", "port", port)
	if err := http.ListenAndServe(":"+port, r); err != nil {
		logger.Error("server_failed", "error", err.Error())
		os.Exit(1)
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func splitHostPort(addr string) (string, int) {
	host, portStr := "localhost", "6379"
	for i := len(addr) - 1; i >= 0; i-- {
		if addr[i] == ':' {
			host = addr[:i]
			portStr = addr[i+1:]
			break
		}
	}
	port, _ := strconv.Atoi(portStr)
	return host, port
}
