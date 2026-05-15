import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { ssepService, ZoneDensity, WaitEstimate } from '../services/SSEPService';
import { useCrowdDensity } from '../hooks/useSSEPData';

const CONGESTION_COLORS: Record<string, string> = {
  low: '#4CAF50',
  moderate: '#FF9800',
  high: '#F44336',
  critical: '#9C27B0',
};

type Tab = 'crowd' | 'waits' | 'navigate' | 'order';

export const DashboardScreen: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('crowd');
  const { zones, loading, criticalZones } = useCrowdDensity();
  const [waitEstimates, setWaitEstimates] = useState<WaitEstimate[]>([]);
  const [bestGate, setBestGate] = useState<any>(null);
  const [menu, setMenu] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      if (activeTab === 'waits') {
        const data = await ssepService.getShortestWait('concession');
        setWaitEstimates([data]);
      } else if (activeTab === 'navigate') {
        const gate = await ssepService.getBestEntryGate();
        setBestGate(gate);
      } else if (activeTab === 'order') {
        const data = await ssepService.getMenu();
        setMenu(data.items);
      }
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'order' && menu.length === 0) {
      ssepService.getMenu().then(data => setMenu(data.items));
    }
    if (activeTab === 'navigate' && !bestGate) {
      ssepService.getBestEntryGate().then(setBestGate);
    }
  }, [activeTab]);

  const renderCrowdMap = () => (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Live Crowd Density</Text>
      {criticalZones.length > 0 && (
        <View style={styles.alertBanner}>
          <Text style={styles.alertText}>
            {criticalZones.length} zone(s) with high congestion
          </Text>
        </View>
      )}
      <FlatList
        data={Array.from(zones.values())}
        keyExtractor={item => item.zone_id}
        renderItem={({ item }) => (
          <View style={[styles.zoneCard, { borderLeftColor: CONGESTION_COLORS[item.congestion_level] || '#999' }]}>
            <View style={styles.zoneInfo}>
              <Text style={styles.zoneName}>{item.zone_id}</Text>
              <Text style={styles.zoneDetail}>{item.headcount} people</Text>
            </View>
            <View style={[styles.congestionBadge, { backgroundColor: CONGESTION_COLORS[item.congestion_level] }]}>
              <Text style={styles.congestionText}>{item.congestion_level.toUpperCase()}</Text>
            </View>
          </View>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      />
    </View>
  );

  const renderWaitTimes = () => (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Wait Time Estimates</Text>
      <FlatList
        data={waitEstimates}
        keyExtractor={item => item.facility_id}
        renderItem={({ item }) => (
          <View style={styles.waitCard}>
            <Text style={styles.waitFacility}>{item.facility_id}</Text>
            <Text style={styles.waitTime}>{item.estimated_wait_minutes} min</Text>
            <Text style={styles.waitConfidence}>{Math.round(item.confidence * 100)}% confidence</Text>
            {item.shorter_alternatives.length > 0 && (
              <View style={styles.alternatives}>
                <Text style={styles.altLabel}>Shorter nearby options:</Text>
                {item.shorter_alternatives.map(alt => (
                  <Text key={alt.facility_id} style={styles.altItem}>
                    {alt.facility_id} ({alt.zone_id}) - {alt.estimated_wait_minutes} min
                  </Text>
                ))}
              </View>
            )}
          </View>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      />
    </View>
  );

  const renderNavigate = () => (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Best Entry Gate</Text>
      {bestGate && (
        <View style={styles.gateCard}>
          <Text style={styles.gateName}>{bestGate.gate_id}</Text>
          <Text style={styles.gateDetail}>
            {bestGate.scans_per_minute} scans/min - {bestGate.status}
          </Text>
          <Text style={styles.gateRec}>{bestGate.recommendation}</Text>
        </View>
      )}
    </View>
  );

  const renderOrder = () => (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>Seat-Side Ordering</Text>
      <FlatList
        data={menu}
        keyExtractor={item => item.item_id}
        numColumns={2}
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.menuCard}>
            <Text style={styles.menuName}>{item.name}</Text>
            <Text style={styles.menuPrice}>${item.price.toFixed(2)}</Text>
            <Text style={styles.menuCategory}>{item.category}</Text>
          </TouchableOpacity>
        )}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      />
    </View>
  );

  const tabs: { key: Tab; label: string }[] = [
    { key: 'crowd', label: 'Crowd' },
    { key: 'waits', label: 'Waits' },
    { key: 'navigate', label: 'Navigate' },
    { key: 'order', label: 'Order' },
  ];

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Smart Stadium</Text>
        {criticalZones.length > 0 && (
          <View style={styles.alertDot} />
        )}
      </View>
      <View style={styles.tabBar}>
        {tabs.map(tab => (
          <TouchableOpacity
            key={tab.key}
            style={[styles.tab, activeTab === tab.key && styles.tabActive]}
            onPress={() => setActiveTab(tab.key)}
          >
            <Text style={[styles.tabText, activeTab === tab.key && styles.tabTextActive]}>
              {tab.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
      <View style={styles.content}>
        {activeTab === 'crowd' && renderCrowdMap()}
        {activeTab === 'waits' && renderWaitTimes()}
        {activeTab === 'navigate' && renderNavigate()}
        {activeTab === 'order' && renderOrder()}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#121212' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    backgroundColor: '#1E1E1E',
  },
  headerTitle: { color: '#FFF', fontSize: 20, fontWeight: '700' },
  alertDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#F44336' },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: '#1E1E1E',
    paddingBottom: 8,
  },
  tab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: { borderBottomColor: '#2196F3' },
  tabText: { color: '#999', fontSize: 13, fontWeight: '500' },
  tabTextActive: { color: '#FFF' },
  content: { flex: 1 },
  section: { flex: 1, padding: 12 },
  sectionTitle: { color: '#FFF', fontSize: 18, fontWeight: '600', marginBottom: 12 },
  alertBanner: {
    backgroundColor: '#F44336',
    padding: 10,
    borderRadius: 8,
    marginBottom: 12,
  },
  alertText: { color: '#FFF', fontSize: 14, fontWeight: '600' },
  zoneCard: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#2C2C2C',
    padding: 12,
    borderRadius: 8,
    borderLeftWidth: 4,
    marginBottom: 8,
  },
  zoneInfo: { flex: 1 },
  zoneName: { color: '#FFF', fontSize: 15, fontWeight: '500' },
  zoneDetail: { color: '#999', fontSize: 12, marginTop: 2 },
  congestionBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  congestionText: { color: '#FFF', fontSize: 10, fontWeight: '700' },
  waitCard: {
    backgroundColor: '#2C2C2C',
    padding: 14,
    borderRadius: 8,
    marginBottom: 8,
  },
  waitFacility: { color: '#FFF', fontSize: 15, fontWeight: '500' },
  waitTime: { color: '#2196F3', fontSize: 24, fontWeight: '700', marginTop: 4 },
  waitConfidence: { color: '#999', fontSize: 12, marginTop: 2 },
  alternatives: { marginTop: 8, paddingTop: 8, borderTopColor: '#444', borderTopWidth: 1 },
  altLabel: { color: '#FF9800', fontSize: 12, fontWeight: '600' },
  altItem: { color: '#CCC', fontSize: 12, marginTop: 4 },
  gateCard: {
    backgroundColor: '#2C2C2C',
    padding: 16,
    borderRadius: 8,
  },
  gateName: { color: '#FFF', fontSize: 22, fontWeight: '700' },
  gateDetail: { color: '#999', fontSize: 14, marginTop: 4 },
  gateRec: { color: '#4CAF50', fontSize: 14, marginTop: 8, fontWeight: '600' },
  menuCard: {
    flex: 1,
    backgroundColor: '#2C2C2C',
    padding: 12,
    borderRadius: 8,
    margin: 4,
    maxWidth: '48%',
  },
  menuName: { color: '#FFF', fontSize: 14, fontWeight: '500' },
  menuPrice: { color: '#2196F3', fontSize: 16, fontWeight: '700', marginTop: 4 },
  menuCategory: { color: '#999', fontSize: 11, marginTop: 2 },
});
