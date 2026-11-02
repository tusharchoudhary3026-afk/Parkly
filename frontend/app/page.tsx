"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Lot = { id: string; name: string; address: string; available_count: number; price_preview: string; forecast: string; area_id?: string | null; area_name?: string | null; venue_id?: string | null; venue_name?: string | null; venue_data_label?: string | null };
type LocationState = { id: string; name: string; code: string; kind: string };
type LocationCity = { id: string; name: string; state_id: string; source: string };
type LocationArea = { id: string; name: string; city_id: string; source: string };
type LocationVenue = { id: string; name: string; area_id: string; venue_type: string; data_label: string; source: string };
type LocationSearchResult = { level: "city" | "area" | "venue"; id: string; name: string; state_id: string; state: string; city_id: string; city?: string; area_id: string | null; area?: string; venue_id: string | null; venue_type?: string; data_label?: string };
type LocationSuggestion = { id: string; target_level: string; state_id: string; city_name: string; area_name?: string | null; venue_name?: string | null; venue_type?: string | null; status: string };
type Booking = { id: string; lot_id: string; slot_id: string; starts_at: string; ends_at: string; status: string; price_preview: string; allocation_reason: string };
type Notice = { id: string; kind: string; message: string; read: boolean };
type OperatorSummary = { revenue_total: string; revenue_sample_size: number; completed_bookings: number; average_completed_duration_minutes: number; occupancy_by_weekday_hour: { weekday_hour: string; mean_occupancy_rate: number; n: number }[]; occupancy_by_location: { lot: string; floor: number; zone: string; vehicle_type: string; capacity: number; occupied: number; available: number }[]; peak_hours: { weekday_hour: string; mean_occupancy_rate: number; n: number }[]; allocation_strategy_kpis: { strategy: string; lot_id: string; n: number; utilization_rate: number; mean_wasted_rank: number }[] };
type Flag = { id: string; booking_id: string; type: string; status: string; label: string };
type AssistedVehicle = { id: string; plate_masked: string; vehicle_type: string };
type ConfigVersion = { version: number; configuration: { strategy?: string; tariff?: Record<string, unknown>; config?: Record<string, unknown> }; changed_by: string; created_at: string };
type Directions = { lot: string; address: string; slot_code: string; floor: number; zone: string; instructions: string; label: string };
type ApiError = { detail?: { message?: string; error?: string } };

const locationCopy = {
  heading: "Choose your location",
  state: "State / union territory",
  city: "City",
  area: "Area / locality",
  venue: "Mall / building / venue (optional)",
  other: "Other - enter manually",
  search: "Search a place",
  searchPlaceholder: "City, area, or venue",
  searchAction: "Search",
  chooseState: "Choose a state",
  chooseCity: "Choose a city",
  chooseArea: "Choose an area",
  anyVenue: "Any venue in this area",
  loadingAction: "Searching…",
  loading: "Loading locations…",
  empty: "No locations listed at this level yet.",
  noLots: "No parking lots are listed here yet.",
  cityName: "City name",
  areaName: "Area / locality name",
  venueName: "Mall / building / venue name",
  venueType: "Venue type",
  suggestTitle: "Suggest a location",
  sendSuggestion: "Send suggestion for review",
  noOwnSuggestions: "No location suggestions submitted yet.",
  noManagerSuggestions: "No pending location suggestions.",
  reviewReason: "Review reason",
  approve: "Approve",
  reject: "Reject",
  assignVenue: "Assign a listed venue to a lot",
  chooseAreaFirst: "Choose the state, city, and area above first. Saving creates a configuration revision and audit entry.",
  saveLocation: "Save lot location",
  venueTypes: ["mall", "building", "market", "hospital", "station", "office", "other"] as const,
} as const;

function localDateTime(value: Date): string {
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

async function failure(response: Response, fallback: string): Promise<Error> {
  const body = (await response.json().catch(() => ({}))) as ApiError;
  return new Error(body.detail?.message ?? body.detail?.error ?? fallback);
}

export default function Home() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [role, setRole] = useState("");
  const [registering, setRegistering] = useState(false);
  const [consentAccepted, setConsentAccepted] = useState(false);
  const [lots, setLots] = useState<Lot[]>([]);
  const [locationStates, setLocationStates] = useState<LocationState[]>([]);
  const [locationCities, setLocationCities] = useState<LocationCity[]>([]);
  const [locationAreas, setLocationAreas] = useState<LocationArea[]>([]);
  const [locationVenues, setLocationVenues] = useState<LocationVenue[]>([]);
  const [selectedStateId, setSelectedStateId] = useState("");
  const [selectedCityId, setSelectedCityId] = useState("");
  const [selectedAreaId, setSelectedAreaId] = useState("");
  const [selectedVenueId, setSelectedVenueId] = useState("");
  const [locationLoading, setLocationLoading] = useState(false);
  const [locationError, setLocationError] = useState("");
  const [searchPlace, setSearchPlace] = useState("");
  const [locationMatches, setLocationMatches] = useState<LocationSearchResult[]>([]);
  const [manualLevel, setManualLevel] = useState<"city" | "area" | "venue" | "">("");
  const [manualLocationName, setManualLocationName] = useState("");
  const [manualVenueType, setManualVenueType] = useState("mall");
  const [locationNotice, setLocationNotice] = useState("");
  const [locationSuggestions, setLocationSuggestions] = useState<LocationSuggestion[]>([]);
  const [reviewReasons, setReviewReasons] = useState<Record<string, string>>({});
  const [noLotsForLocation, setNoLotsForLocation] = useState(false);
  const [configVenueId, setConfigVenueId] = useState("");
  const [selectedLot, setSelectedLot] = useState("");
  const [plate, setPlate] = useState("");
  const [vehicleType, setVehicleType] = useState("car");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [minimumStart, setMinimumStart] = useState("");
  const [minimumEnd, setMinimumEnd] = useState("");
  const [pendingBooking, setPendingBooking] = useState<Booking | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [operatorSummary, setOperatorSummary] = useState<OperatorSummary | null>(null);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [attendantBookingId, setAttendantBookingId] = useState("");
  const [attendantPlate, setAttendantPlate] = useState("");
  const [qrToken, setQrToken] = useState("");
  const [gatewayOffline, setGatewayOffline] = useState(false);
  const [configLotId, setConfigLotId] = useState("");
  const [configJson, setConfigJson] = useState('{"grace_minutes":10,"max_duration_hours":24,"repeated_no_show_threshold":3,"long_overstay_minutes":30,"many_cancellations_threshold":3,"recommendation_weights":{"price":0.4,"distance":0.3,"availability":0.3}}');
  const [tariffJson, setTariffJson] = useState('{"free_minutes":0,"hourly":{"car":40},"daily":{"car":320}}');
  const [strategy, setStrategy] = useState("first_fit");
  const [driverEmail, setDriverEmail] = useState("");
  const [assistedVehicles, setAssistedVehicles] = useState<AssistedVehicle[]>([]);
  const [assistedVehicleId, setAssistedVehicleId] = useState("");
  const [assistedLotId, setAssistedLotId] = useState("");
  const [newLotName, setNewLotName] = useState("");
  const [newLotAddress, setNewLotAddress] = useState("");
  const [dashboardStart, setDashboardStart] = useState("");
  const [dashboardEnd, setDashboardEnd] = useState("");
  const [slotBatchCount, setSlotBatchCount] = useState(20);
  const [slotBatchType, setSlotBatchType] = useState("car");
  const [configHistory, setConfigHistory] = useState<ConfigVersion[]>([]);
  const [penaltyAmount, setPenaltyAmount] = useState("0");
  const [penaltyReason, setPenaltyReason] = useState("");
  const [penaltyConfirmed, setPenaltyConfirmed] = useState(false);
  const [bookingMode, setBookingMode] = useState<"reserve" | "park-now">("reserve");
  const [slotDirections, setSlotDirections] = useState<Record<string, Directions>>({});
  const [message, setMessage] = useState("Create an account or sign in to find parking.");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) void navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    const start = new Date();
    start.setMinutes(0, 0, 0);
    start.setHours(start.getHours() + 1);
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    const startValue = localDateTime(start);
    const endValue = localDateTime(end);
    setMinimumStart(startValue);
    setMinimumEnd(endValue);
    setStartsAt(startValue);
    setEndsAt(endValue);
  }, []);

  async function loadBookings(accessToken: string) {
    const response = await fetch(`${api}/bookings`, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (response.ok) setBookings((await response.json()) as Booking[]);
  }

  async function loadLocations(accessToken: string) {
    setLocationLoading(true); setLocationError("");
    try {
      const response = await fetch(`${api}/locations/states`, { headers: { Authorization: `Bearer ${accessToken}` } });
      if (!response.ok) throw await failure(response, "Could not load locations.");
      const states = (await response.json()) as LocationState[];
      setLocationStates(states);
      let remembered: { stateId?: string; cityId?: string; areaId?: string; venueId?: string } = {};
      try { remembered = JSON.parse(localStorage.getItem("parkly-location-v1") ?? "{}"); } catch { remembered = {}; }
      const state = states.find((item) => item.id === remembered.stateId) ?? states.find((item) => item.code === "MP") ?? states[0];
      if (!state) return;
      setSelectedStateId(state.id);
      const cityResponse = await fetch(`${api}/locations/states/${state.id}/cities`, { headers: { Authorization: `Bearer ${accessToken}` } });
      if (!cityResponse.ok) throw await failure(cityResponse, "Could not load cities.");
      const cities = (await cityResponse.json()) as LocationCity[];
      setLocationCities(cities);
      const city = cities.find((item) => item.id === remembered.cityId) ??
        (state.code === "MP" ? cities.find((item) => item.name === "Gwalior") : undefined) ?? cities[0];
      setSelectedCityId(city?.id ?? "");
      if (city) {
        const areaResponse = await fetch(`${api}/locations/cities/${city.id}/areas`, { headers: { Authorization: `Bearer ${accessToken}` } });
        if (!areaResponse.ok) throw await failure(areaResponse, "Could not load areas.");
        const areas = (await areaResponse.json()) as LocationArea[];
        setLocationAreas(areas);
        const area = areas.find((item) => item.id === remembered.areaId);
        setSelectedAreaId(area?.id ?? "");
        if (area) {
          const venueResponse = await fetch(`${api}/locations/areas/${area.id}/venues`, { headers: { Authorization: `Bearer ${accessToken}` } });
          if (!venueResponse.ok) throw await failure(venueResponse, "Could not load venues.");
          const venues = (await venueResponse.json()) as LocationVenue[];
          setLocationVenues(venues);
          setSelectedVenueId(venues.some((item) => item.id === remembered.venueId) ? remembered.venueId ?? "" : "");
        } else { setLocationVenues([]); setSelectedVenueId(""); }
      } else { setLocationAreas([]); setLocationVenues([]); setSelectedAreaId(""); setSelectedVenueId(""); }
    } catch (error) {
      setLocationError(error instanceof Error ? error.message : "Could not load locations.");
    } finally { setLocationLoading(false); }
  }

  async function loadLocationSuggestions(accessToken: string) {
    const response = await fetch(`${api}/locations/suggestions`, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (response.ok) setLocationSuggestions((await response.json()) as LocationSuggestion[]);
  }

  const refreshLots = useCallback(async (accessToken: string) => {
    const params = new URLSearchParams({ vehicle_type: vehicleType });
    if (selectedStateId) params.set("state_id", selectedStateId);
    if (selectedCityId) params.set("city_id", selectedCityId);
    if (selectedAreaId) params.set("area_id", selectedAreaId);
    if (selectedVenueId) params.set("venue_id", selectedVenueId);
    if (startsAt && endsAt) {
      params.set("starts_at", new Date(startsAt).toISOString());
      params.set("ends_at", new Date(endsAt).toISOString());
    }
    const response = await fetch(`${api}/lots?${params}`, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (response.ok) {
      const rows = (await response.json()) as Lot[];
      setLots(rows);
      setSelectedLot((current) => rows.some((lot) => lot.id === current) ? current : "");
    } else setLocationError("Could not load parking lots for this location.");
  }, [vehicleType, startsAt, endsAt, selectedStateId, selectedCityId, selectedAreaId, selectedVenueId]);

  useEffect(() => {
    if (token && startsAt && endsAt && !locationLoading && selectedCityId && !locationNotice) void refreshLots(token);
  }, [token, refreshLots, locationLoading, selectedCityId, locationNotice]);

  useEffect(() => {
    if (!selectedStateId) return;
    try { localStorage.setItem("parkly-location-v1", JSON.stringify({ stateId:selectedStateId, cityId:selectedCityId, areaId:selectedAreaId, venueId:selectedVenueId })); }
    catch { /* Storage may be blocked; location selection still works in memory. */ }
  }, [selectedStateId, selectedCityId, selectedAreaId, selectedVenueId]);

  async function loadNotices(accessToken: string) {
    const response = await fetch(`${api}/notifications`, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (response.ok) setNotices((await response.json()) as Notice[]);
  }

  async function loadOperatorData(accessToken: string, accessRole: string) {
    const headers = { Authorization: `Bearer ${accessToken}` };
    if (["manager", "auditor"].includes(accessRole)) {
      const range = new URLSearchParams();
      if (dashboardStart && dashboardEnd) {
        range.set("start_at", new Date(`${dashboardStart}T00:00:00`).toISOString());
        range.set("end_at", new Date(`${dashboardEnd}T23:59:59`).toISOString());
      }
      const summary = await fetch(`${api}/operator/dashboard${range.size ? `?${range}` : ""}`, { headers });
      if (summary.ok) setOperatorSummary((await summary.json()) as OperatorSummary);
      const audit = await fetch(`${api}/operator/audit`, { headers });
      if (audit.ok) setMessage("Operations view loaded. Occupancy and forecasts are software-recorded estimates.");
    }
    if (["manager", "auditor"].includes(accessRole)) {
      const response = await fetch(`${api}/operator/flags`, { headers });
      if (response.ok) setFlags((await response.json()) as Flag[]);
    }
    await loadLocationSuggestions(accessToken);
  }

  async function changeLocationState(stateId: string) {
    setSelectedStateId(stateId); setSelectedCityId(""); setSelectedAreaId(""); setSelectedVenueId("");
    setLocationCities([]); setLocationAreas([]); setLocationVenues([]); setLocationNotice(""); setManualLevel("");
    setNoLotsForLocation(false); setConfigVenueId("");
    if (!stateId || !token) return;
    setLocationLoading(true); setLocationError("");
    try {
      const response = await fetch(`${api}/locations/states/${stateId}/cities`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw await failure(response, "Could not load cities.");
      setLocationCities((await response.json()) as LocationCity[]);
    } catch (error) { setLocationError(error instanceof Error ? error.message : "Could not load cities."); }
    finally { setLocationLoading(false); }
  }

  async function changeLocationCity(cityId: string) {
    setSelectedCityId(cityId); setSelectedAreaId(""); setSelectedVenueId(""); setLocationAreas([]); setLocationVenues([]);
    setLocationNotice(""); setManualLevel(""); setNoLotsForLocation(false); setConfigVenueId("");
    if (!cityId || !token) return;
    setLocationLoading(true); setLocationError("");
    try {
      const response = await fetch(`${api}/locations/cities/${cityId}/areas`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw await failure(response, "Could not load areas.");
      setLocationAreas((await response.json()) as LocationArea[]);
    } catch (error) { setLocationError(error instanceof Error ? error.message : "Could not load areas."); }
    finally { setLocationLoading(false); }
  }

  async function changeLocationArea(areaId: string) {
    setSelectedAreaId(areaId); setSelectedVenueId(""); setConfigVenueId(""); setLocationVenues([]); setLocationNotice(""); setManualLevel(""); setNoLotsForLocation(false);
    if (!areaId || !token) return;
    setLocationLoading(true); setLocationError("");
    try {
      const response = await fetch(`${api}/locations/areas/${areaId}/venues`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw await failure(response, "Could not load venues.");
      setLocationVenues((await response.json()) as LocationVenue[]);
    } catch (error) { setLocationError(error instanceof Error ? error.message : "Could not load venues."); }
    finally { setLocationLoading(false); }
  }

  async function searchLocations(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || searchPlace.trim().length < 2) return;
    setLocationLoading(true); setLocationError(""); setLocationMatches([]);
    try {
      const response = await fetch(`${api}/locations/search?q=${encodeURIComponent(searchPlace.trim())}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw await failure(response, "Could not search locations.");
      const results = (await response.json()) as LocationSearchResult[];
      setLocationMatches(results);
      if (!results.length) setLocationError(locationCopy.empty);
    } catch (error) { setLocationError(error instanceof Error ? error.message : "Could not search locations."); }
    finally { setLocationLoading(false); }
  }

  async function chooseSearchResult(result: LocationSearchResult) {
    if (!token) return;
    setLocationLoading(true); setLocationError(""); setLocationNotice(""); setManualLevel("");
    setNoLotsForLocation(false); setConfigVenueId("");
    setSelectedStateId(result.state_id); setSelectedCityId(result.city_id); setSelectedAreaId(result.area_id ?? "");
    setSelectedVenueId(result.venue_id ?? "");
    try {
      const cityResponse = await fetch(`${api}/locations/states/${result.state_id}/cities`, { headers: { Authorization: `Bearer ${token}` } });
      if (!cityResponse.ok) throw await failure(cityResponse, "Could not load the selected city.");
      setLocationCities((await cityResponse.json()) as LocationCity[]);
      const areaResponse = await fetch(`${api}/locations/cities/${result.city_id}/areas`, { headers: { Authorization: `Bearer ${token}` } });
      if (!areaResponse.ok) throw await failure(areaResponse, "Could not load the selected area.");
      setLocationAreas((await areaResponse.json()) as LocationArea[]);
      if (result.area_id) {
        const venueResponse = await fetch(`${api}/locations/areas/${result.area_id}/venues`, { headers: { Authorization: `Bearer ${token}` } });
        if (!venueResponse.ok) throw await failure(venueResponse, "Could not load venues.");
        setLocationVenues((await venueResponse.json()) as LocationVenue[]);
      } else { setLocationVenues([]); }
    } catch (error) { setLocationError(error instanceof Error ? error.message : "Could not select that place."); }
    finally { setLocationLoading(false); }
  }

  async function submitLocationSuggestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedStateId || !manualLevel || manualLocationName.trim().length < 2) return;
    const body: Record<string, string> = { state_id:selectedStateId, target_level:manualLevel };
    if (manualLevel === "city") body.city_name = manualLocationName.trim();
    if (manualLevel === "area") { body.city_id = selectedCityId; body.area_name = manualLocationName.trim(); }
    if (manualLevel === "venue") { body.area_id = selectedAreaId; body.venue_name = manualLocationName.trim(); body.venue_type = manualVenueType; }
    setBusy(true); setLocationError("");
    try {
      const response = await fetch(`${api}/locations/suggestions`, { method:"POST", headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`}, body:JSON.stringify(body) });
      if (!response.ok) throw await failure(response, "Could not send this location suggestion.");
      const result = (await response.json()) as { message: string };
      setLocationNotice(result.message); setNoLotsForLocation(true); setLots([]); setSelectedLot("");
      setManualLevel(""); setManualLocationName("");
      await loadLocationSuggestions(token);
    } catch (error) { setLocationError(error instanceof Error ? error.message : "Could not send this location suggestion."); }
    finally { setBusy(false); }
  }

  async function reviewLocationSuggestion(suggestionId: string, decision: "approve" | "reject") {
    if (!token || reviewReasons[suggestionId]?.trim().length < 3) return;
    const response = await fetch(`${api}/locations/suggestions/${suggestionId}/review`, { method:"POST",
      headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`},
      body:JSON.stringify({decision,reason:reviewReasons[suggestionId].trim()}) });
    if (!response.ok) { setMessage("Could not review this location suggestion."); return; }
    setReviewReasons((current) => ({...current,[suggestionId]:""}));
    setMessage(`Location suggestion ${decision}d with an audit record.`);
    await loadLocationSuggestions(token);
  }

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage("Connecting to the parking service…");
    try {
      const response = await fetch(`${api}/auth/${registering ? "register" : "token"}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(registering ? { email, password, consent_accepted: consentAccepted } : { email, password }) });
      if (!response.ok) throw await failure(response, "Could not sign in.");
      const data = (await response.json()) as { access_token: string; role: string };
      setToken(data.access_token);
      setRole(data.role);
      await loadLocations(data.access_token);
      await loadBookings(data.access_token);
      await loadNotices(data.access_token);
      await loadOperatorData(data.access_token, data.role);
      setMessage("You’re signed in. Availability is an estimate based on parking records.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Connection failed."); }
    finally { setBusy(false); }
  }

  async function reserve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selectedLot) return;
    setBusy(true); setMessage("Checking availability and calculating your price…"); setPendingBooking(null);
    try {
      const vehicleResponse = await fetch(`${api}/vehicles`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ plate, vehicle_type: vehicleType }) });
      if (!vehicleResponse.ok) throw await failure(vehicleResponse, "Could not add that vehicle.");
      const vehicle = (await vehicleResponse.json()) as { id: string };
      const response = await fetch(`${api}/bookings`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ lot_id: selectedLot, vehicle_id: vehicle.id, starts_at: new Date(startsAt).toISOString(), ends_at: new Date(endsAt).toISOString(), idempotency_key: crypto.randomUUID() }) });
      if (!response.ok) throw await failure(response, "Could not reserve a space.");
      const booking = (await response.json()) as Booking;
      setPendingBooking(booking);
      setMessage("Review the exact total below. Your booking is held temporarily and is not confirmed yet.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not create a booking hold."); }
    finally { setBusy(false); }
  }

  async function confirmBooking() {
    if (!token || !pendingBooking) return;
    setBusy(true); setMessage("Confirming your booking…");
    try {
      const response = await fetch(`${api}/bookings/${pendingBooking.id}/confirm`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw await failure(response, "Could not confirm this booking.");
      setPendingBooking(null); setMessage("Booking confirmed. You can find it in your booking history."); await loadBookings(token);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not confirm this booking."); }
    finally { setBusy(false); }
  }

  async function bookingAction(booking: Booking, action: "pay" | "cancel") {
    if (!token) return;
    setBusy(true);
    try {
      const response = await fetch(`${api}/bookings/${booking.id}/${action === "pay" ? "payments" : "cancel"}`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(action === "pay" ? { confirmed: true, method: "upi", idempotency_key: crypto.randomUUID() } : { reason: "Driver cancelled from booking history" }),
      });
      if (!response.ok) throw await failure(response, `Could not ${action} booking.`);
      setMessage(action === "pay" ? "TEST MODE payment recorded; no money was taken." : "Booking cancelled.");
      await loadBookings(token);
    } catch (error) { setMessage(error instanceof Error ? error.message : `Could not ${action} booking.`); }
    finally { setBusy(false); }
  }

  async function viewReceipt(bookingId: string) {
    if (!token) return;
    const response = await fetch(`${api}/bookings/${bookingId}/receipt`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { setMessage("Could not load receipt."); return; }
    const url = URL.createObjectURL(await response.blob());
    window.open(url, "_blank", "noopener,noreferrer");
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  function startParkNow() {
    const start = new Date(Date.now() + 60_000);
    start.setSeconds(0, 0);
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    const startValue = localDateTime(start); const endValue = localDateTime(end);
    setBookingMode("park-now"); setStartsAt(startValue); setEndsAt(endValue); setMinimumStart(startValue); setMinimumEnd(endValue);
  }

  async function showDirections(bookingId: string) {
    if (!token) return;
    const response = await fetch(`${api}/bookings/${bookingId}/directions`, { headers: { Authorization: `Bearer ${token}` } });
    if (response.ok) {
      const directions = (await response.json()) as Directions;
      setSlotDirections((current) => ({ ...current, [bookingId]: directions }));
    }
  }

  async function reviewFlag(flagId: string, decision: "dismiss" | "warn" | "escalate") {
    if (!token) return;
    const response = await fetch(`${api}/operator/flags/${flagId}/review`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ decision, reason: `Manager review: ${decision}` }) });
    if (!response.ok) { setMessage("Could not save exception review."); return; }
    await loadOperatorData(token, role);
  }

  async function recordReviewedPenalty(flagId: string) {
    if (!token || !penaltyConfirmed || !penaltyReason.trim()) return;
    const response = await fetch(`${api}/operator/flags/${flagId}/penalty`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ amount: Number(penaltyAmount), reason: penaltyReason, confirmed: penaltyConfirmed }) });
    if (!response.ok) { setMessage("Penalty decision was not recorded. The flag must be escalated first."); return; }
    setPenaltyConfirmed(false); setPenaltyReason(""); setMessage("Human-reviewed decision recorded and driver notified."); await loadOperatorData(token, role);
  }

  async function saveLotConfiguration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !configLotId) return;
    try {
      const pickerVenue = locationVenues.find((venue) => venue.id === configVenueId);
      const response = await fetch(`${api}/operator/lots/${configLotId}/configuration`, { method: "PUT", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ config: JSON.parse(configJson), tariff: JSON.parse(tariffJson), strategy, area_id: pickerVenue?.area_id ?? selectedAreaId ?? null, venue_id: configVenueId || null }) });
      if (!response.ok) throw await failure(response, "Could not save lot settings.");
      const result = (await response.json()) as { version: number };
      setMessage(`Configuration saved as version ${result.version}. New bookings use the updated tariff.`);
      const historyResponse=await fetch(`${api}/operator/lots/${configLotId}/configuration/history`,{headers:{Authorization:`Bearer ${token}`}});
      if(historyResponse.ok) setConfigHistory((await historyResponse.json()) as ConfigVersion[]);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Settings JSON is invalid."); }
  }

  async function selectConfigLot(lotId: string) {
    setConfigLotId(lotId); setConfigHistory([]);
    const selected = lots.find((lot) => lot.id === lotId);
    setConfigVenueId(selected?.venue_id ?? "");
    if (selected?.area_id && token) {
      setSelectedAreaId(selected.area_id);
      const venueResponse = await fetch(`${api}/locations/areas/${selected.area_id}/venues`, { headers:{Authorization:`Bearer ${token}`} });
      if (venueResponse.ok) setLocationVenues((await venueResponse.json()) as LocationVenue[]);
    }
    if (!token || !lotId) return;
    const response=await fetch(`${api}/operator/lots/${lotId}/configuration/history`,{headers:{Authorization:`Bearer ${token}`}});
    if(response.ok) setConfigHistory((await response.json()) as ConfigVersion[]);
  }

  async function saveLotLocation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !configLotId) return;
    const venue = locationVenues.find((item) => item.id === configVenueId);
    const response = await fetch(`${api}/operator/lots/${configLotId}/location`, { method:"PUT",
      headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`},
      body:JSON.stringify({area_id:venue?.area_id ?? (selectedAreaId || null),venue_id:configVenueId || null}) });
    if (!response.ok) { setMessage("Could not update this lot’s venue. Choose an approved venue and area."); return; }
    setMessage("Lot location saved as a new audited configuration revision.");
    await refreshLots(token);
  }

  async function createLot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    try {
      const response = await fetch(`${api}/operator/lots`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ name: newLotName, address: newLotAddress, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, config: JSON.parse(configJson), tariff: JSON.parse(tariffJson), strategy, area_id:selectedAreaId || null, venue_id:selectedVenueId || null }) });
      if (!response.ok) throw await failure(response, "Could not create lot.");
      const created = (await response.json()) as { id: string };
      setConfigLotId(created.id); setMessage("Lot created. Add its parking slots through the operator API or Swagger page.");
      await refreshLots(token);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not create lot."); }
  }

  async function createSlotBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !configLotId) return;
    const items = Array.from({ length: slotBatchCount }, (_, index) => ({ slot_code: `P-${String(index + 1).padStart(3, "0")}`, floor: Math.floor(index / 20), zone: "A", slot_type: slotBatchType, exit_rank: index, ev_only: slotBatchType === "ev", accessible_only: slotBatchType === "accessible" }));
    const response = await fetch(`${api}/operator/lots/${configLotId}/slots`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(items) });
    if (!response.ok) { setMessage("Could not create slots. Slot codes must be unique within this lot."); return; }
    const result = (await response.json()) as { created: number };
    setMessage(`Created ${result.created} parking slots.`);
  }

  async function attendantAction(action: "check-in" | "check-out" | "qr") {
    if (!token) return;
    const path = action === "qr" ? "/attendant/qr/check-in" : `/attendant/bookings/${attendantBookingId}/check-${action === "check-in" ? "in" : "out"}${action === "check-out" ? `?reason=${encodeURIComponent(gatewayOffline ? "payment gateway simulated unavailable" : "attendant checkout")}&gateway_available=${!gatewayOffline}` : ""}`;
    const response = await fetch(`${api}${path}`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: action === "qr" ? JSON.stringify({ qr_token: qrToken }) : undefined });
    if (!response.ok) { setMessage("Attendant action failed. Check the booking or QR pass and role."); return; }
    if (action === "check-out") {
      const result = (await response.json()) as { bill: string; fallback: boolean };
      setMessage(`Checkout recorded. Final bill ₹${result.bill} · ${result.fallback ? "gateway fallback: pay at exit" : "TEST MODE gateway"}.`);
    } else setMessage("Entry action recorded.");
  }

  async function lookupAttendantPlate() {
    if (!token || !attendantPlate) return;
    const response = await fetch(`${api}/attendant/plate/${encodeURIComponent(attendantPlate)}/active-booking`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { setMessage("No active booking found for that plate."); return; }
    const matches = (await response.json()) as { booking_id: string; status: string; plate_masked: string }[];
    if (matches[0]) { setAttendantBookingId(matches[0].booking_id); setMessage(`Booking found for ${matches[0].plate_masked} · ${matches[0].status}.`); }
    else setMessage("No confirmed booking found for that vehicle.");
  }

  async function findDriverVehicles() {
    if (!token || !driverEmail) return;
    const response = await fetch(`${api}/attendant/drivers/${encodeURIComponent(driverEmail)}/vehicles`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) { setMessage("Could not find that driver's vehicles for this operator."); return; }
    const items = (await response.json()) as AssistedVehicle[];
    setAssistedVehicles(items); setAssistedVehicleId(items[0]?.id ?? "");
  }

  async function createAssistedBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !startsAt || !endsAt) return;
    const response = await fetch(`${api}/attendant/bookings`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify({ driver_email: driverEmail, vehicle_id: assistedVehicleId, lot_id: assistedLotId, starts_at: new Date(startsAt).toISOString(), ends_at: new Date(endsAt).toISOString(), idempotency_key: crypto.randomUUID() }) });
    if (!response.ok) { setMessage("Could not create the assisted booking hold."); return; }
    setMessage("Assisted hold created. The driver must sign in and explicitly confirm it.");
  }

  return <main className="shell">
    <header className="topbar"><a className="brand" href="#home" aria-label="Parkly home"><span className="brand-mark">P</span> parkly</a><nav aria-label="Main navigation"><a href="#find">Find parking</a><a href="#about">How it works</a>{token && <a href="#history">My bookings</a>}</nav><span className="mode">TEST MODE</span></header>
    <section className="hero" id="home"><div className="hero-copy"><p className="eyebrow">PARKING, WITH A PLAN</p><h1>Your spot,<br/><em>already sorted.</em></h1><p className="intro">Reserve a space for the time you need. See the price up front and arrive with a clear plan.</p><a className="button primary" href="#find">Find a parking spot <span aria-hidden="true">↗</span></a><div className="trust"><span className="check">✓</span><span>Clear prices, human-reviewed exceptions</span></div></div><div className="hero-art" aria-label="Illustration of a reserved parking space"><div className="sun"/><div className="cloud c1"/><div className="cloud c2"/><div className="sign"><span>P</span><small>YOUR SPOT</small></div><div className="road"><div className="parking-line"/><div className="car"><div className="car-top"/><div className="car-body"><b>●</b><b>●</b></div></div><div className="road-dash"/></div><div className="art-caption">A smoother arrival starts here</div></div></section>
    <section className="principles" id="about"><div><span className="number">01</span><h2>Know before you go</h2><p>Availability and exact price are shown before you confirm.</p></div><div><span className="number">02</span><h2>Time that works for you</h2><p>Choose a window that fits your day, with a grace period.</p></div><div><span className="number">03</span><h2>People stay in control</h2><p>Exceptions go to a human reviewer. No automatic fines.</p></div></section>
    <section className="find" id="find"><div className="section-heading"><div><p className="eyebrow">A GOOD PLACE TO START</p><h2>Find your space</h2></div><span className="estimate">ESTIMATE · Availability can change</span></div>
      <div className="search-card">
        {!token ? <><form className="auth-form" onSubmit={authenticate}><label htmlFor="email">Email address</label><input id="email" autoComplete="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com"/><label htmlFor="password">Password</label><input id="password" autoComplete={registering ? "new-password" : "current-password"} type="password" minLength={12} required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="12 characters or more"/>{registering && <label className="consent"><input type="checkbox" required checked={consentAccepted} onChange={(e) => setConsentAccepted(e.target.checked)}/><span>I have read the privacy notice. Parkly uses my account and booking details to provide this demo service.</span></label>}<button className="button primary" type="submit" disabled={busy}>{busy ? "Please wait…" : registering ? "Create driver account" : "Sign in to search"}</button></form><button className="text-button" type="button" onClick={() => { setRegistering(!registering); setMessage(registering ? "Create an account or sign in to find parking." : "Create a driver account with your email and a 12-character password."); }}>{registering ? "Already have an account? Sign in" : "New to Parkly? Create an account"}</button></> : <>
          <section className="location-picker" aria-labelledby="locationHeading">
            <h3 id="locationHeading">{locationCopy.heading}</h3>
            <form className="location-search" onSubmit={searchLocations}><label htmlFor="placeSearch">{locationCopy.search}</label><div><input id="placeSearch" type="search" minLength={2} maxLength={80} value={searchPlace} onChange={(event) => setSearchPlace(event.target.value)} placeholder={locationCopy.searchPlaceholder}/><button className="button outline" type="submit" disabled={busy || locationLoading}>{locationCopy.searchAction}</button></div></form>
            {locationMatches.length > 0 && <ul className="location-matches" aria-label="Search results">{locationMatches.map((match) => <li key={`${match.level}-${match.id}`}><button className="text-button" type="button" onClick={() => void chooseSearchResult(match)}>{[match.name,match.area,match.city,match.state].filter(Boolean).join(" · ")}</button></li>)}</ul>}
            <div className="location-fields">
              <div><label htmlFor="locationState">{locationCopy.state}</label><select id="locationState" value={selectedStateId} disabled={locationLoading} onChange={(event) => void changeLocationState(event.target.value)}><option value="">{locationCopy.chooseState}</option>{locationStates.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div>
              <div><label htmlFor="locationCity">{locationCopy.city}</label><select id="locationCity" value={manualLevel === "city" ? "__other__" : selectedCityId} disabled={!selectedStateId || locationLoading} onChange={(event) => { if (event.target.value === "__other__") { setManualLevel("city"); setManualLocationName(""); setLocationNotice(""); setNoLotsForLocation(true); setLots([]); setSelectedLot(""); setSelectedCityId(""); setSelectedAreaId(""); setSelectedVenueId(""); } else void changeLocationCity(event.target.value); }}><option value="">{locationCopy.chooseCity}</option>{locationCities.map((item) => <option key={item.id} value={item.id}>{item.name}{item.source === "user_submitted" ? " · USER_SUBMITTED" : ""}</option>)}<option value="__other__">{locationCopy.other}</option></select></div>
              <div><label htmlFor="locationArea">{locationCopy.area}</label><select id="locationArea" value={manualLevel === "area" ? "__other__" : selectedAreaId} disabled={!selectedCityId || locationLoading} onChange={(event) => { if (event.target.value === "__other__") { setManualLevel("area"); setManualLocationName(""); setLocationNotice(""); setNoLotsForLocation(true); setLots([]); setSelectedLot(""); setSelectedAreaId(""); setSelectedVenueId(""); } else void changeLocationArea(event.target.value); }}><option value="">{locationCopy.chooseArea}</option>{locationAreas.map((item) => <option key={item.id} value={item.id}>{item.name}{item.source === "user_submitted" ? " · USER_SUBMITTED" : ""}</option>)}<option value="__other__">{locationCopy.other}</option></select></div>
              <div><label htmlFor="locationVenue">{locationCopy.venue}</label><select id="locationVenue" value={manualLevel === "venue" ? "__other__" : selectedVenueId} disabled={!selectedAreaId || locationLoading} onChange={(event) => { if (event.target.value === "__other__") { setManualLevel("venue"); setManualLocationName(""); setLocationNotice(""); setNoLotsForLocation(true); setLots([]); setSelectedLot(""); setSelectedVenueId(""); } else { setManualLevel(""); setLocationNotice(""); setNoLotsForLocation(false); setSelectedVenueId(event.target.value); } }}><option value="">{locationCopy.anyVenue}</option>{locationVenues.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.data_label}</option>)}<option value="__other__">{locationCopy.other}</option></select></div>
            </div>
            <p className="location-status" role="status" aria-live="polite">{locationLoading ? locationCopy.loading : locationError || (locationAreas.length === 0 && selectedCityId ? locationCopy.empty : "")}</p>
            {manualLevel && <form className="manual-location" onSubmit={submitLocationSuggestion}><strong>{locationCopy.suggestTitle} · {manualLevel}</strong><label htmlFor="manualLocationName">{manualLevel === "city" ? locationCopy.cityName : manualLevel === "area" ? locationCopy.areaName : locationCopy.venueName}</label><input id="manualLocationName" required minLength={2} maxLength={80} pattern="[A-Za-z0-9À-ž .,&'()\-]{2,80}" value={manualLocationName} onChange={(event) => setManualLocationName(event.target.value)} placeholder={locationCopy.cityName}/>{manualLevel === "venue" && <><label htmlFor="manualVenueType">{locationCopy.venueType}</label><select id="manualVenueType" value={manualVenueType} onChange={(event) => setManualVenueType(event.target.value)}>{locationCopy.venueTypes.map((type) => <option key={type} value={type}>{type[0].toUpperCase() + type.slice(1)}</option>)}</select></>}<button className="button outline" type="submit" disabled={busy || locationLoading}>{locationCopy.sendSuggestion}</button></form>}
            {role !== "manager" && <div className="my-location-suggestions"><b>My location suggestions</b>{locationSuggestions.length ? locationSuggestions.map((suggestion) => <p key={suggestion.id}>{[suggestion.city_name,suggestion.area_name,suggestion.venue_name].filter(Boolean).join(" · ")} · {suggestion.status}</p>) : <p>{locationCopy.noOwnSuggestions}</p>}</div>}
            {locationNotice && <p className="location-notice" role="status" aria-live="polite">{locationNotice}</p>}
          </section>
          {noLotsForLocation ? <p className="location-empty">{locationNotice || locationCopy.noLots}</p> : <div className="lot-list" aria-label="Available parking lots">{lots.map((lot) => <article className={`lot-card ${selectedLot === lot.id ? "selected" : ""}`} key={lot.id}><div><h3>{lot.name}</h3><p>{lot.address}</p>{lot.venue_name && <p className="venue-label"><span>{lot.venue_data_label}</span> · {lot.venue_name}</p>}</div><div className="lot-meta"><b>{lot.available_count} spaces</b><span>{lot.forecast}</span></div><strong>₹{lot.price_preview} <small>/ hour preview</small></strong><button className="button outline" type="button" aria-pressed={selectedLot === lot.id} onClick={() => { setSelectedLot(lot.id); setPendingBooking(null); }}>{selectedLot === lot.id ? "Selected" : "Choose this lot"}</button></article>)}</div>}
          {selectedLot && <form className="booking-form" onSubmit={reserve}><h3>{bookingMode === "park-now" ? "Park now" : "Choose your time"}</h3><p className="field-help">{[locationStates.find((item) => item.id === selectedStateId)?.name,locationCities.find((item) => item.id === selectedCityId)?.name,locationAreas.find((item) => item.id === selectedAreaId)?.name,locationVenues.find((item) => item.id === selectedVenueId)?.name].filter(Boolean).join(" · ")}</p><div className="operation-actions"><button className="button outline" type="button" onClick={startParkNow}>Park now · next available minute</button><button className="button outline" type="button" onClick={() => setBookingMode("reserve")}>Reserve a future time</button></div><div className="booking-fields"><div><label htmlFor="plate">Vehicle plate</label><input id="plate" required maxLength={24} value={plate} onChange={(e) => setPlate(e.target.value)} placeholder="Enter plate number"/></div><div><label htmlFor="vehicleType">Vehicle type</label><select id="vehicleType" value={vehicleType} onChange={(e) => setVehicleType(e.target.value)}><option value="two_wheeler">Two wheeler</option><option value="car">Car</option><option value="large">Large / SUV</option><option value="ev">EV</option><option value="accessible">Accessible</option></select></div><div><label htmlFor="startsAt">Start time</label><input id="startsAt" type="datetime-local" required min={minimumStart} value={startsAt} onChange={(e) => { const next = e.target.value; setBookingMode("reserve"); setStartsAt(next); if (next) { const adjusted = new Date(next); adjusted.setHours(adjusted.getHours() + 1); const nextEnd = localDateTime(adjusted); setMinimumEnd(nextEnd); if (endsAt < nextEnd) setEndsAt(nextEnd); } }}/></div><div><label htmlFor="endsAt">End time</label><input id="endsAt" type="datetime-local" required min={minimumEnd} value={endsAt} onChange={(e) => setEndsAt(e.target.value)}/></div></div><p className="field-help">Choose a future start time and an end time at least one hour later. Times use your device’s local timezone.</p><button className="button primary" type="submit" disabled={busy}>{busy ? "Checking…" : "Preview price & hold space"}</button></form>}
          {pendingBooking && <div className="price-confirm" role="group" aria-label="Booking price confirmation"><div><span>Exact price for this time window</span><strong>₹{pendingBooking.price_preview}</strong><small>TEST MODE · No payment is taken</small></div><p>{pendingBooking.allocation_reason}</p><button className="button primary" type="button" onClick={confirmBooking} disabled={busy}>Confirm booking</button><button className="button outline" type="button" onClick={() => { setPendingBooking(null); setMessage("The temporary hold will expire if you do not confirm."); }}>Cancel</button></div>}
        </>}
        <p className="status" role="status" aria-live="polite">{message}</p>
      </div>
    </section>
    {token && <section className="history" id="history"><div className="section-heading"><div><p className="eyebrow">YOUR PARKING PLANS</p><h2>My bookings</h2></div></div>{bookings.length ? <div className="lot-list">{bookings.map((booking) => <article className="history-card" key={booking.id}><div><h3>{lots.find((lot) => lot.id === booking.lot_id)?.name ?? "Parking lot"}</h3><p>{new Date(booking.starts_at).toLocaleString()} – {new Date(booking.ends_at).toLocaleString()}</p><button className="text-button" type="button" onClick={() => void viewReceipt(booking.id)}>View receipt</button><button className="text-button" type="button" onClick={() => void showDirections(booking.id)}>My Slot directions</button>{slotDirections[booking.id] && <p className="directions">{slotDirections[booking.id].instructions}<br/>{slotDirections[booking.id].address}. {slotDirections[booking.id].label}</p>}</div><span className={`booking-status ${booking.status}`}>{booking.status.replaceAll("_", " ")}</span><strong>₹{booking.price_preview}</strong>{booking.status === "confirmed" && <button className="button outline" type="button" disabled={busy} onClick={() => bookingAction(booking, "pay")}>Pay · TEST MODE</button>}{["held", "confirmed"].includes(booking.status) && <button className="button outline" type="button" disabled={busy} onClick={() => bookingAction(booking, "cancel")}>Cancel booking</button>}</article>)}</div> : <p className="status">No bookings yet. Choose a lot and time to get started.</p>}<div className="notice-list"><h3>Notifications</h3>{notices.length ? notices.map((notice) => <p key={notice.id}>{notice.read ? "✓ " : "• "}{notice.message}</p>) : <p>No notifications yet.</p>}</div></section>}
    {token && ["manager", "auditor"].includes(role) && <section className="operations"><div className="section-heading"><div><p className="eyebrow">OPERATOR WORKSPACE · {role.toUpperCase()}</p><h2>Parking operations</h2></div><a className="button outline" href={`${api}/operator/export/bookings.csv`} onClick={(event) => { event.preventDefault(); if (token) void fetch(`${api}/operator/export/bookings.csv`, { headers: { Authorization: `Bearer ${token}` } }).then(async (response) => { if (response.ok) { const url = URL.createObjectURL(await response.blob()); const link = document.createElement("a"); link.href = url; link.download = "parkly-bookings.csv"; link.click(); URL.revokeObjectURL(url); } }); }}>Export bookings CSV</a></div>{operatorSummary && <><div className="date-filter"><label htmlFor="dashboardStart">From</label><input id="dashboardStart" type="date" value={dashboardStart} onChange={(event) => setDashboardStart(event.target.value)}/><label htmlFor="dashboardEnd">To</label><input id="dashboardEnd" type="date" value={dashboardEnd} onChange={(event) => setDashboardEnd(event.target.value)}/><button className="button outline" type="button" onClick={() => void loadOperatorData(token, role)}>Apply date range</button></div><div className="metrics"><article><span>Completed revenue · n={operatorSummary.revenue_sample_size}</span><strong>₹{operatorSummary.revenue_total}</strong></article><article><span>Completed bookings</span><strong>{operatorSummary.completed_bookings}</strong></article><article><span>Average stay</span><strong>{operatorSummary.average_completed_duration_minutes} min</strong></article></div><h3>Allocation strategy sample</h3><div className="operation-list">{operatorSummary.allocation_strategy_kpis.map((item) => <p key={item.strategy}><b>{item.strategy}</b> · n={item.n} · mean wasted rank {item.mean_wasted_rank}</p>)}</div><h3>Live occupancy by lot, floor, zone, and vehicle type</h3><div className="operation-list">{operatorSummary.occupancy_by_location.map((item) => <p key={`${item.lot}-${item.floor}-${item.zone}-${item.vehicle_type}`}>{item.lot} · floor {item.floor} · zone {item.zone} · {item.vehicle_type}: {item.occupied}/{item.capacity} occupied</p>)}</div><h3>Peak occupancy hours · estimates</h3><div className="operation-list">{operatorSummary.peak_hours.map((item) => <p key={item.weekday_hour}>{item.weekday_hour}: {Math.round(item.mean_occupancy_rate * 100)}% · n={item.n}</p>)}</div><h3>Weekday and hour occupancy · estimates</h3><div className="operation-grid">{operatorSummary.occupancy_by_weekday_hour.map((item) => <span key={item.weekday_hour} title={`n=${item.n}`}>{item.weekday_hour}<b>{Math.round(item.mean_occupancy_rate * 100)}%</b></span>)}</div></>}{role === "manager" && <><h3>Lot pricing and allocation settings</h3><form className="config-form" onSubmit={saveLotConfiguration}><label htmlFor="configLot">Lot</label><select id="configLot" required value={configLotId} onChange={(event) => void selectConfigLot(event.target.value)}><option value="">Choose a lot</option>{lots.map((lot) => <option key={lot.id} value={lot.id}>{lot.name}</option>)}</select><label htmlFor="lotStrategy">Allocation strategy</label><select id="lotStrategy" value={strategy} onChange={(event) => setStrategy(event.target.value)}><option value="first_fit">First Fit</option><option value="best_fit">Best Fit</option><option value="scored">Weighted scoring</option></select><label htmlFor="lotConfigJson">Grace, duration and recommendation settings (JSON)</label><textarea id="lotConfigJson" rows={4} value={configJson} onChange={(event) => setConfigJson(event.target.value)}/><label htmlFor="lotTariffJson">Tariff (JSON)</label><textarea id="lotTariffJson" rows={4} value={tariffJson} onChange={(event) => setTariffJson(event.target.value)}/><button className="button primary" type="submit">Save new version</button></form><div className="operation-list"><b>Configuration history</b>{configHistory.map((entry) => <p key={entry.version}>Version {entry.version} · {entry.configuration.strategy} · {new Date(entry.created_at).toLocaleString()}</p>)}</div><h3>Create parking lot</h3><form className="config-form" onSubmit={createLot}><label htmlFor="newLotName">Lot name</label><input id="newLotName" minLength={2} required value={newLotName} onChange={(event) => setNewLotName(event.target.value)}/><label htmlFor="newLotAddress">Address</label><input id="newLotAddress" minLength={3} required value={newLotAddress} onChange={(event) => setNewLotAddress(event.target.value)}/><button className="button outline" type="submit">Create lot</button></form><form className="config-form" onSubmit={createSlotBatch}><label htmlFor="slotBatchCount">Create slots for selected lot · count (1–500)</label><input id="slotBatchCount" type="number" min={1} max={500} value={slotBatchCount} onChange={(event) => setSlotBatchCount(Number(event.target.value))}/><label htmlFor="slotBatchType">Slot type</label><select id="slotBatchType" value={slotBatchType} onChange={(event) => setSlotBatchType(event.target.value)}><option value="two_wheeler">Two wheeler</option><option value="car">Car</option><option value="large">Large / SUV</option><option value="ev">EV only</option><option value="accessible">Accessible only</option></select><button className="button outline" type="submit" disabled={!configLotId}>Create slots</button></form><h3>Human review queue</h3>{flags.length ? flags.map((flag) => <article className="operation-row" key={flag.id}><span>{flag.type} · {flag.status} · {flag.label}</span>{flag.status === "open" && <div><button className="button outline" type="button" onClick={() => void reviewFlag(flag.id, "dismiss")}>Dismiss</button><button className="button outline" type="button" onClick={() => void reviewFlag(flag.id, "warn")}>Warn</button><button className="button outline" type="button" onClick={() => void reviewFlag(flag.id, "escalate")}>Escalate</button></div>}{flag.status === "escalate" && <form className="penalty-form" onSubmit={(event) => { event.preventDefault(); void recordReviewedPenalty(flag.id); }}><label htmlFor={`penaltyAmount-${flag.id}`}>Manager-approved amount (INR)</label><input id={`penaltyAmount-${flag.id}`} type="number" min="1" step="0.01" value={penaltyAmount} onChange={(event) => setPenaltyAmount(event.target.value)}/><label htmlFor={`penaltyReason-${flag.id}`}>Decision reason</label><textarea id={`penaltyReason-${flag.id}`} minLength={3} required value={penaltyReason} onChange={(event) => setPenaltyReason(event.target.value)}/><label className="consent"><input type="checkbox" checked={penaltyConfirmed} onChange={(event) => setPenaltyConfirmed(event.target.checked)}/><span>I am the manager and explicitly approve this human-reviewed decision.</span></label><button className="button outline" type="submit" disabled={!penaltyConfirmed}>Record reviewed decision</button></form>}</article>) : <p>No exceptions awaiting review.</p>}</>}</section>}
    {token && ["attendant", "manager"].includes(role) && <section className="operations"><p className="eyebrow">ATTENDANT TOOLS · SOFTWARE RECORDED</p><h2>Entry and exit</h2><div className="operation-actions"><label htmlFor="attendantPlate">Find active booking by plate</label><input id="attendantPlate" value={attendantPlate} onChange={(event) => setAttendantPlate(event.target.value)} placeholder="Vehicle plate"/><button className="button outline" type="button" onClick={() => void lookupAttendantPlate()}>Find booking</button></div><label htmlFor="attendantBooking">Booking ID</label><input id="attendantBooking" value={attendantBookingId} onChange={(event) => setAttendantBookingId(event.target.value)} placeholder="Paste booking ID"/><div className="operation-actions"><button className="button outline" type="button" disabled={!attendantBookingId} onClick={() => void attendantAction("check-in")}>Check in</button><button className="button outline" type="button" disabled={!attendantBookingId} onClick={() => void attendantAction("check-out")}>Check out</button></div><label className="consent"><input type="checkbox" checked={gatewayOffline} onChange={(event) => setGatewayOffline(event.target.checked)}/><span>Simulate unavailable payment gateway and test pay-at-exit fallback</span></label><label htmlFor="qrToken">QR pass token</label><input id="qrToken" value={qrToken} onChange={(event) => setQrToken(event.target.value)} placeholder="Paste scanned QR token"/><button className="button outline" type="button" disabled={!qrToken} onClick={() => void attendantAction("qr")}>Verify QR and check in</button><h3>Assisted booking</h3><div className="operation-actions"><input type="email" aria-label="Driver email" value={driverEmail} onChange={(event) => setDriverEmail(event.target.value)} placeholder="Driver email"/><button className="button outline" type="button" onClick={() => void findDriverVehicles()}>Find vehicles</button></div>{assistedVehicles.length > 0 && <form className="config-form" onSubmit={createAssistedBooking}><label htmlFor="assistLot">Parking lot</label><select id="assistLot" required value={assistedLotId} onChange={(event) => setAssistedLotId(event.target.value)}><option value="">Choose a lot</option>{lots.map((lot) => <option key={lot.id} value={lot.id}>{lot.name}</option>)}</select><label htmlFor="assistVehicle">Driver vehicle · masked plate</label><select id="assistVehicle" value={assistedVehicleId} onChange={(event) => setAssistedVehicleId(event.target.value)}>{assistedVehicles.map((vehicle) => <option key={vehicle.id} value={vehicle.id}>{vehicle.vehicle_type} · {vehicle.plate_masked}</option>)}</select><button className="button primary" type="submit">Create driver confirmation hold</button></form>}</section>}
    {token && role === "manager" && <section className="operations location-operations"><p className="eyebrow">SHARED LOCATION DATA · HUMAN REVIEW</p><h2>Location suggestions</h2>{locationSuggestions.length ? locationSuggestions.map((suggestion) => <article className="location-review" key={suggestion.id}><div><b>{suggestion.target_level.toUpperCase()}</b><p>{[suggestion.city_name,suggestion.area_name,suggestion.venue_name].filter(Boolean).join(" · ")}</p><small>Status: {suggestion.status}</small></div>{suggestion.status === "pending" && <><label htmlFor={`locationReason-${suggestion.id}`}>Review reason</label><input id={`locationReason-${suggestion.id}`} minLength={3} maxLength={500} required value={reviewReasons[suggestion.id] ?? ""} onChange={(event) => setReviewReasons((current) => ({...current,[suggestion.id]:event.target.value}))}/><div className="operation-actions"><button className="button outline" type="button" disabled={(reviewReasons[suggestion.id] ?? "").trim().length < 3} onClick={() => void reviewLocationSuggestion(suggestion.id,"approve")}>Approve</button><button className="button outline" type="button" disabled={(reviewReasons[suggestion.id] ?? "").trim().length < 3} onClick={() => void reviewLocationSuggestion(suggestion.id,"reject")}>Reject</button></div></>}</article>) : <p>No pending location suggestions.</p>}<h3>Assign a listed venue to a lot</h3><form className="config-form" onSubmit={saveLotLocation}><label htmlFor="locationConfigLot">Lot</label><select id="locationConfigLot" required value={configLotId} onChange={(event) => void selectConfigLot(event.target.value)}><option value="">Choose a lot</option>{lots.map((lot) => <option key={lot.id} value={lot.id}>{lot.name}</option>)}</select><label htmlFor="locationConfigVenue">Venue in the selected area</label><select id="locationConfigVenue" value={configVenueId} disabled={!selectedAreaId} onChange={(event) => setConfigVenueId(event.target.value)}><option value="">No specific venue</option>{locationVenues.map((venue) => <option key={venue.id} value={venue.id}>{venue.name} · {venue.data_label}</option>)}</select><p className="field-help">Choose the state, city, and area above first. Saving creates a configuration revision and audit entry.</p><button className="button outline" type="submit" disabled={!configLotId}>Save lot location</button></form></section>}
    <footer><span>parkly</span><span>Software-only demo · Synthetic data is labelled · No sensors or cameras</span><a href={`${api}/docs`}>API documentation</a></footer>
  </main>;
}
