'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { HeatLayer, type HeatLatLng } from 'leaflet.heat';
import 'leaflet/dist/leaflet.css';

export type HeatPoint = {
  lat: number;
  lng: number;
  weight: number;
  label: string;
  source: string;
  confidence: number;
};

type Props = {
  points: HeatPoint[];
};

const US_CENTER: L.LatLngExpression = [39.8, -98.5];
const US_ZOOM = 4;

export function HeatmapMap({ points }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const heatRef = useRef<HeatLayer | null>(null);

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
    // leaflet.heat typings don't fully mirror Layer; runtime is a Leaflet layer.
    map.addLayer(heat as unknown as L.Layer);

    mapRef.current = map;
    heatRef.current = heat;

    return () => {
      map.remove();
      mapRef.current = null;
      heatRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const heat = heatRef.current;
    if (!map || !heat) return;

    const latlngs: HeatLatLng[] = points.map((p) => [p.lat, p.lng, p.weight]);
    heat.setLatLngs(latlngs);

    if (points.length === 1) {
      map.setView([points[0].lat, points[0].lng], 7);
    } else if (points.length > 1) {
      const bounds = L.latLngBounds(points.map((p) => L.latLng(p.lat, p.lng)));
      map.fitBounds(bounds.pad(0.35), { maxZoom: 8 });
    } else {
      map.setView(US_CENTER, US_ZOOM);
    }
  }, [points]);

  return <div ref={containerRef} className="heat-map-canvas" />;
}
