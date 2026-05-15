import { useState, useEffect, useRef } from 'react';
import { ssepService, ZoneDensity } from '../services/SSEPService';

export function useCrowdDensity() {
  const [zones, setZones] = useState<Map<string, ZoneDensity>>(new Map());
  const [loading, setLoading] = useState(true);
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    unsubRef.current = ssepService.subscribeToCrowdUpdates(updatedZones => {
      setZones(updatedZones);
      setLoading(false);
    });

    return () => {
      if (unsubRef.current) {
        unsubRef.current();
      }
    };
  }, []);

  const criticalZones = Array.from(zones.values()).filter(
    z => z.congestion_level === 'critical' || z.congestion_level === 'high',
  );

  return { zones, loading, criticalZones };
}

export function useOrderStatus(orderId: string | null) {
  const [order, setOrder] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!orderId) {
      setLoading(false);
      return;
    }

    unsubRef.current = ssepService.subscribeToOrderUpdates(orderId, updated => {
      setOrder(updated);
      setLoading(false);
    });

    return () => {
      if (unsubRef.current) {
        unsubRef.current();
      }
    };
  }, [orderId]);

  return { order, loading };
}
