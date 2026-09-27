import type { FeatureCollection } from "geojson";
import { cellToBoundary } from "h3-js";
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import SectorSheet from "../components/SectorSheet";
import { t } from "../i18n";
import { useStore } from "../store";
import { haptic, webApp } from "../tg";
import type { MapCitiesResponse, MapSectorsResponse } from "../types";

// MapLibre 6 derives its worker URL from import.meta.url at runtime, which a bundler
// cannot see; let Vite bundle the worker and point MapLibre at the result.
maplibregl.setWorkerUrl(workerUrl);

const SECTOR_MIN_ZOOM = 7.5;
const MAX_SECTOR_SPAN_DEG = 6;
const POLL_MS = 15_000;
const NEUTRAL_COLOR = "#9aa3b5";
const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

function styleUrl(): string {
  const dark = (webApp()?.colorScheme ?? "dark") === "dark";
  return `https://tiles.openfreemap.org/styles/${dark ? "dark" : "liberty"}`;
}

function sectorsToGeoJson(data: MapSectorsResponse, myClanId: number | undefined): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: data.sectors.map(([h3, clanId, defense, value, shield]) => {
      const ring = cellToBoundary(h3, true);
      ring.push(ring[0]);
      const clan = clanId !== null ? data.clans[String(clanId)] : undefined;
      const strength = clan ? Math.min(1, Math.log10(defense + 1) / 6) : 0;
      return {
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [ring] },
        properties: {
          h3,
          color: clan?.color ?? NEUTRAL_COLOR,
          opacity: clan ? 0.3 + 0.35 * strength : 0.06,
          mine: clanId !== null && clanId === myClanId ? 1 : 0,
          value,
          shield,
        },
      };
    }),
  };
}

function citiesToGeoJson(data: MapCitiesResponse): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: data.cities.map((c) => {
      const clan = c.controller_clan_id !== null ? data.clans[String(c.controller_clan_id)] : undefined;
      return {
        type: "Feature",
        geometry: { type: "Point", coordinates: [c.lng, c.lat] },
        properties: { id: c.id, name: c.name, population: c.population, color: clan?.color ?? NEUTRAL_COLOR },
      };
    }),
  };
}

// Used when the basemap tile server is unreachable: the game layers still work.
const FALLBACK_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#0d1320" } }],
};

function addGameLayers(map: maplibregl.Map): void {
  if (map.getSource("sectors")) return;
  map.addSource("sectors", { type: "geojson", data: EMPTY });
  map.addSource("cities", { type: "geojson", data: EMPTY });
  map.addLayer({
    id: "sector-fill",
    type: "fill",
    source: "sectors",
    minzoom: SECTOR_MIN_ZOOM,
    paint: { "fill-color": ["get", "color"], "fill-opacity": ["get", "opacity"] },
  });
  map.addLayer({
    id: "sector-line",
    type: "line",
    source: "sectors",
    minzoom: SECTOR_MIN_ZOOM,
    paint: {
      "line-color": ["get", "color"],
      "line-opacity": 0.8,
      "line-width": ["case", ["==", ["get", "mine"], 1], 2.2, 0.8],
    },
  });
  map.addLayer({
    id: "sector-selected",
    type: "line",
    source: "sectors",
    minzoom: SECTOR_MIN_ZOOM,
    filter: ["==", ["get", "h3"], ""],
    paint: { "line-color": "#ffffff", "line-width": 3 },
  });
  map.addLayer({
    id: "city-circle",
    type: "circle",
    source: "cities",
    maxzoom: SECTOR_MIN_ZOOM,
    paint: {
      "circle-color": ["get", "color"],
      "circle-opacity": 0.85,
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1,
      "circle-radius": ["interpolate", ["linear"], ["get", "population"], 15000, 3, 1000000, 8, 10000000, 14],
    },
  });
}

export default function MapScreen() {
  const state = useStore((s) => s.state);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [zoomedOut, setZoomedOut] = useState(false);
  const myClanId = state?.clan?.id;
  const clanRef = useRef(myClanId);
  clanRef.current = myClanId;

  const refresh = useCallback(async () => {
    const map = mapRef.current;
    if (!map || !map.getSource("sectors")) return;
    const b = map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((x) => x.toFixed(4)).join(",");
    const zoom = map.getZoom();
    setZoomedOut(zoom < SECTOR_MIN_ZOOM);
    try {
      if (zoom >= SECTOR_MIN_ZOOM && b.getEast() - b.getWest() <= MAX_SECTOR_SPAN_DEG) {
        const data = await api<MapSectorsResponse>(`/map/sectors?bbox=${bbox}`);
        (map.getSource("sectors") as maplibregl.GeoJSONSource | undefined)?.setData(
          sectorsToGeoJson(data, clanRef.current),
        );
      } else {
        const data = await api<MapCitiesResponse>(`/map/cities?bbox=${bbox}`);
        (map.getSource("cities") as maplibregl.GeoJSONSource | undefined)?.setData(citiesToGeoJson(data));
      }
    } catch {
      /* transient network errors: the next poll retries */
    }
  }, []);

  useEffect(() => {
    if (!containerRef.current || !state?.city) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleUrl(),
      center: [state.city.lng, state.city.lat],
      zoom: 9.3,
      minZoom: 2,
      maxZoom: 13,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      attributionControl: { compact: true, customAttribution: "Cities: GeoNames (CC BY 4.0)" },
    });
    map.touchZoomRotate.disableRotation();
    mapRef.current = map;

    // Re-add game layers whenever a style (the basemap or the fallback) finishes loading.
    map.on("style.load", () => {
      addGameLayers(map);
      void refresh();
    });
    let fellBack = false;
    map.on("error", () => {
      if (!fellBack && !map.isStyleLoaded()) {
        fellBack = true;
        map.setStyle(FALLBACK_STYLE);
      }
    });

    let timer: ReturnType<typeof setTimeout> | undefined;
    map.on("moveend", () => {
      clearTimeout(timer);
      timer = setTimeout(() => void refresh(), 250);
    });
    map.on("click", "sector-fill", (e) => {
      const h3 = e.features?.[0]?.properties?.h3 as string | undefined;
      if (!h3) return;
      haptic("select");
      map.setFilter("sector-selected", ["==", ["get", "h3"], h3]);
      setSelected(h3);
    });
    map.on("click", "city-circle", (e) => {
      const geom = e.features?.[0]?.geometry;
      if (geom?.type === "Point") map.flyTo({ center: geom.coordinates as [number, number], zoom: 9.3 });
    });
    for (const layer of ["sector-fill", "city-circle"]) {
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }

    const poll = setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, POLL_MS);

    return () => {
      clearInterval(poll);
      clearTimeout(timer);
      map.remove();
      mapRef.current = null;
    };
    // The map is created once per mount; the home city does not change during a session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh]);

  const goHome = () => {
    if (state?.city) mapRef.current?.flyTo({ center: [state.city.lng, state.city.lat], zoom: 9.3 });
  };

  return (
    <div className="map-screen">
      <div ref={containerRef} className="map-container" />
      {zoomedOut && <div className="map-hint">{t("map.zoomIn")}</div>}
      <button className="map-home" onClick={goHome}>
        📍 {t("map.home")}
      </button>
      <SectorSheet
        h3={selected}
        onClose={() => {
          setSelected(null);
          mapRef.current?.setFilter("sector-selected", ["==", ["get", "h3"], ""]);
        }}
        onChanged={() => void refresh()}
      />
    </div>
  );
}
