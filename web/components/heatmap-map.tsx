'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { HeatLayer, type HeatLatLng } from 'leaflet.heat';
import 'leaflet/dist/leaflet.css';

export type HeatPoint = {
  id: string;
  kind: 'message' | 'session';
  lat: number;
  lng: number;
  weight: number;
  label: string;
  source: string;
  confidence: number;
  category?: string;
  campaignId?: string;
  status?: string;
  text?: string;
  sessionId?: string;
  /** Where to draw this point's heat, if different from its marker position. */
  heatLat?: number;
  heatLng?: number;
};

export type CustomerPoint = {
  id: string;
  lat: number;
  lng: number;
  name: string;
  city: string;
  state: string;
};

export type OriginCluster = {
  key: string;
  lat: number;
  lng: number;
  label: string;
  points: HeatPoint[];
};

type Props = {
  points: HeatPoint[];
  customers: CustomerPoint[];
  showCustomers: boolean;
  selectedKey: string | null;
  onSelectCluster: (cluster: OriginCluster | null) => void;
};

const US_CENTER: L.LatLngExpression = [39.8, -98.5];
const US_ZOOM = 4;

export function clusterKey(lat: number, lng: number) {
  return `${lat.toFixed(4)},${lng.toFixed(4)}`;
}

function buildClusters(points: HeatPoint[]): OriginCluster[] {
  const map = new Map<string, OriginCluster>();
  for (const point of points) {
    const key = clusterKey(point.lat, point.lng);
    const existing = map.get(key);
    if (existing) {
      existing.points.push(point);
    } else {
      map.set(key, {
        key,
        lat: point.lat,
        lng: point.lng,
        label: point.label,
        points: [point],
      });
    }
  }
  return [...map.values()];
}

export function HeatmapMap({
  points,
  customers,
  showCustomers,
  selectedKey,
  onSelectCluster,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const heatRef = useRef<HeatLayer | null>(null);
  const originLayerRef = useRef<L.LayerGroup | null>(null);
  const customerLayerRef = useRef<L.LayerGroup | null>(null);
  const onSelectRef = useRef(onSelectCluster);
  onSelectRef.current = onSelectCluster;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: US_CENTER,
      zoom: US_ZOOM,
      zoomControl: true,
      attributionControl: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);

    const heat = new HeatLayer([], {
      radius: 28,
      blur: 22,
      maxZoom: 10,
      minOpacity: 0.35,
      max: 1,
      gradient: {
        0.2: '#7C3E93',
        0.45: '#E20074',
        0.7: '#FF2E9B',
        1.0: '#F58220',
      },
    });
    map.addLayer(heat as unknown as L.Layer);

    const originLayer = L.layerGroup().addTo(map);
    const customerLayer = L.layerGroup().addTo(map);

    map.on('click', () => onSelectRef.current(null));

    mapRef.current = map;
    heatRef.current = heat;
    originLayerRef.current = originLayer;
    customerLayerRef.current = customerLayer;

    return () => {
      map.remove();
      mapRef.current = null;
      heatRef.current = null;
      originLayerRef.current = null;
      customerLayerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const heat = heatRef.current;
    const originLayer = originLayerRef.current;
    if (!heat || !originLayer) return;

    const clusters = buildClusters(points);
    const latlngs: HeatLatLng[] = points.map((p) => [p.heatLat ?? p.lat, p.heatLng ?? p.lng, p.weight]);
    heat.setLatLngs(latlngs);

    originLayer.clearLayers();
    for (const cluster of clusters) {
      const selected = cluster.key === selectedKey;
      const marker = L.circleMarker([cluster.lat, cluster.lng], {
        radius: Math.min(18, 7 + cluster.points.length * 2),
        color: selected ? '#111111' : '#E20074',
        weight: selected ? 3 : 1.5,
        fillColor: selected ? '#FF2E9B' : '#E20074',
        fillOpacity: selected ? 0.55 : 0.2,
        opacity: selected ? 1 : 0.55,
      });
      marker.bindTooltip(
        `${cluster.label} · ${cluster.points.length} origin${cluster.points.length === 1 ? '' : 's'}`,
        { direction: 'top', opacity: 0.95 }
      );
      marker.on('click', (event) => {
        L.DomEvent.stopPropagation(event);
        onSelectRef.current(cluster);
      });
      marker.addTo(originLayer);
    }
  }, [points, selectedKey]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (points.length === 1) {
      map.setView([points[0].lat, points[0].lng], 7);
    } else if (points.length > 1) {
      const bounds = L.latLngBounds(points.map((p) => L.latLng(p.lat, p.lng)));
      if (showCustomers && customers.length > 0) {
        for (const c of customers) bounds.extend([c.lat, c.lng]);
      }
      map.fitBounds(bounds.pad(0.35), { maxZoom: 8 });
    } else if (showCustomers && customers.length > 0) {
      const bounds = L.latLngBounds(customers.map((c) => L.latLng(c.lat, c.lng)));
      map.fitBounds(bounds.pad(0.35), { maxZoom: 8 });
    } else {
      map.setView(US_CENTER, US_ZOOM);
    }
  }, [points, showCustomers, customers]);

  useEffect(() => {
    const customerLayer = customerLayerRef.current;
    if (!customerLayer) return;
    customerLayer.clearLayers();
    if (!showCustomers) return;

    for (const customer of customers) {
      const marker = L.circleMarker([customer.lat, customer.lng], {
        radius: 7,
        color: '#0f766e',
        weight: 2,
        fillColor: '#00A19C',
        fillOpacity: 0.85,
      });
      marker.bindTooltip(
        `${customer.name} · ${customer.city}, ${customer.state}`,
        { direction: 'top', opacity: 0.95 }
      );
      marker.addTo(customerLayer);
    }
  }, [customers, showCustomers]);

  return <div ref={containerRef} className="heat-map-canvas" />;
}
