import firestore from '@react-native-firebase/firestore';
import messaging from '@react-native-firebase/messaging';

const VENUE_ID = 'stadium-001';
const API_BASE = 'https://ssep-api.run.app';

export interface ZoneDensity {
  zone_id: string;
  density: number;
  headcount: number;
  congestion_level: 'low' | 'moderate' | 'high' | 'critical';
  last_updated: string;
}

export interface WaitEstimate {
  zone_id: string;
  facility_type: string;
  facility_id: string;
  estimated_wait_minutes: number;
  queue_length: number;
  confidence: number;
  shorter_alternatives: Array<{
    facility_id: string;
    zone_id: string;
    estimated_wait_minutes: number;
  }>;
}

export interface MenuItem {
  item_id: string;
  name: string;
  price: number;
  category: string;
  prep_minutes: number;
}

export interface Order {
  order_id: string;
  status: string;
  items: Array<{ item_id: string; name: string; quantity: number; unit_price: number }>;
  total_amount: number;
  estimated_delivery_minutes: number | null;
  assigned_runner: string | null;
}

export interface RouteStep {
  zone_id: string;
  zone_name: string;
  passage_type: string;
  estimated_seconds: number;
  congestion: number;
}

class SSEPService {
  private attendeeId: string | null = null;

  setAttendeeId(id: string) {
    this.attendeeId = id;
  }

  async requestNotificationPermission(): Promise<boolean> {
    const authStatus = await messaging().requestPermission();
    return authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
      authStatus === messaging.AuthorizationStatus.PROVISIONAL;
  }

  async getFCMToken(): Promise<string> {
    return messaging().getToken();
  }

  subscribeToCrowdUpdates(
    onUpdate: (zones: Map<string, ZoneDensity>) => void,
  ): () => void {
    const subscriber = firestore()
      .collection('crowd_density')
      .where('venue_id', '==', VENUE_ID)
      .onSnapshot(snapshot => {
        const zones = new Map<string, ZoneDensity>();
        snapshot.docs.forEach(doc => {
          const data = doc.data() as ZoneDensity;
          zones.set(data.zone_id, data);
        });
        onUpdate(zones);
      });
    return subscriber;
  }

  subscribeToOrderUpdates(
    orderId: string,
    onUpdate: (order: Order) => void,
  ): () => void {
    const subscriber = firestore()
      .collection('orders')
      .doc(orderId)
      .onSnapshot(snapshot => {
        if (snapshot.exists) {
          onUpdate(snapshot.data() as Order);
        }
      });
    return subscriber;
  }

  async getHeatmap(): Promise<{ zones: ZoneDensity[]; timestamp: string }> {
    const response = await fetch(`${API_BASE}/crowd-flow/api/v1/heatmap`);
    return response.json();
  }

  async getWaitTimes(zoneId: string): Promise<{ wait_times: WaitEstimate[] }> {
    const response = await fetch(
      `${API_BASE}/queue-predictor/api/v1/wait-times/${zoneId}`,
    );
    return response.json();
  }

  async getShortestWait(facilityType: string): Promise<WaitEstimate> {
    const response = await fetch(
      `${API_BASE}/queue-predictor/api/v1/shortest/${facilityType}`,
    );
    return response.json();
  }

  async navigate(
    fromZone: string,
    toZone: string,
    avoidZones?: string[],
  ): Promise<{
    route_id: string;
    steps: RouteStep[];
    total_estimated_seconds: number;
  }> {
    const response = await fetch(`${API_BASE}/navigation/api/v1/navigate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_zone: fromZone, to_zone: toZone, avoid_zones: avoidZones }),
    });
    return response.json();
  }

  async getBestGate(fromZone: string): Promise<any> {
    const response = await fetch(
      `${API_BASE}/navigation/api/v1/best-gate?from=${fromZone}`,
    );
    return response.json();
  }

  async getMenu(): Promise<{ items: MenuItem[] }> {
    const response = await fetch(
      `${API_BASE}/order-deliver/api/v1/menu`,
    );
    return response.json();
  }

  async createOrder(items: Array<{ item_id: string; quantity: number }>, seat: {
    section: string;
    row: string;
    number: string;
  }): Promise<Order> {
    const response = await fetch(`${API_BASE}/order-deliver/api/v1/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        attendee_id: this.attendeeId,
        seat_section: seat.section,
        seat_row: seat.row,
        seat_number: seat.number,
        items: items.map(i => ({
          item_id: i.item_id,
          name: '',
          quantity: i.quantity,
          unit_price: 0,
        })),
      }),
    });
    return response.json();
  }

  async getOrder(orderId: string): Promise<Order> {
    const response = await fetch(
      `${API_BASE}/order-deliver/api/v1/orders/${orderId}`,
    );
    return response.json();
  }

  async getGateStatus(): Promise<any> {
    const response = await fetch(
      `${API_BASE}/gate-entry/api/v1/gates`,
    );
    return response.json();
  }

  async getBestEntryGate(): Promise<any> {
    const response = await fetch(
      `${API_BASE}/gate-entry/api/v1/gates/best-entry`,
    );
    return response.json();
  }
}

export const ssepService = new SSEPService();
export default SSEPService;
