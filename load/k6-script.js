// CivicPulse load test: a fixed *offered* load, to measure how fast the HPA reacts.
//
// ramping-arrival-rate starts requests at the scheduled rate whether or not
// earlier ones have finished, so the load doesn't quietly back off when the
// backend slows down (a closed loop of virtual users would). The offered
// load is therefore exactly the schedule below, which is what the
// replicas-vs-load chart plots.
//
// Run through load/run-load-test.sh, or directly:
//   docker run --rm -i --network k3d-civicpulse -v "$PWD/load:/load" grafana/k6:2.3.0 \
//     run -e BASE_URL=http://k3d-civicpulse-serverlb /load/k6-script.js
import http from "k6/http";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://civicpulse.localhost:8081";
const HOST = __ENV.HOST_HEADER || "civicpulse.localhost";

// Offered load, requests per second. Exported so the chart script uses the same numbers.
export const SCHEDULE = [
  { target: 5, duration: "60s" },    // baseline: well under one replica's share
  { target: 120, duration: "20s" },  // the load arrives
  { target: 120, duration: "240s" }, // and stays
  { target: 5, duration: "20s" },    // the load leaves
  { target: 5, duration: "60s" },    // quiet tail (scale-in continues after k6 stops)
];

export const options = {
  scenarios: {
    offered_load: {
      executor: "ramping-arrival-rate",
      startRate: 5,
      timeUnit: "1s",
      preAllocatedVUs: 60,
      maxVUs: 400,
      stages: SCHEDULE,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],     // under 1 % errors, even while scaling
    http_req_duration: ["p(95)<2000"],
  },
  summaryTrendStats: ["avg", "med", "p(90)", "p(95)", "p(99)", "max"],
};

// Mostly the paginated, filtered list (a real database query per request),
// plus the cached stats and the provider metadata the dashboard also loads.
const CATEGORIES = ["water", "electricity", "sanitation", "roads", "streetlights", "other"];

export default function () {
  const params = { headers: { Host: HOST }, tags: {} };
  const r = Math.random();
  let res;
  if (r < 0.7) {
    const category = CATEGORIES[Math.floor(Math.random() * CATEGORIES.length)];
    const page = 1 + Math.floor(Math.random() * 2);
    params.tags.name = "GET /api/complaints";
    res = http.get(`${BASE_URL}/api/complaints?category=${category}&page=${page}&page_size=20`, params);
  } else if (r < 0.9) {
    params.tags.name = "GET /api/stats";
    res = http.get(`${BASE_URL}/api/stats`, params);
  } else {
    params.tags.name = "GET /api/meta/providers";
    res = http.get(`${BASE_URL}/api/meta/providers`, params);
  }
  check(res, { "status 200": (x) => x.status === 200 });
}
