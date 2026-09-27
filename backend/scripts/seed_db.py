"""Idempotent seed script — populates >=30 realistic complaints.

Idempotency Strategy:
  Each complaint is given a deterministic UUID derived from its seed_key (a
  stable short string). If a row with that UUID already exists, it is skipped.
  Running the seed twice will therefore produce exactly the same row count.

Usage:
  cd backend
  python -m scripts.seed_db

  Or via Docker:
  docker compose exec backend python -m scripts.seed_db
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Deterministic UUID factory ────────────────────────────────────────────────

SEED_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def seed_uuid(seed_key: str) -> uuid.UUID:
    """Generate a stable UUID from a string seed key using UUID5."""
    return uuid.uuid5(SEED_NAMESPACE, seed_key)


# ── Seed data: >=30 realistic Urdu-influenced English complaints ──────────────
# triaged_by uses only production labels (plan §1.2). "simulated" is reserved
# for SimulatedTriage in CI/tests and must not appear in seeded demo data.

COMPLAINTS = [
    {
        "seed_key": "water-001",
        "text": "Paani nahi aa raha pichle teen din se, poori gali pareshan hai. Pump band ho gaya hai.",
        "location": "Gulberg III, Main Boulevard, Block C",
        "category": "water",
        "priority": "high",
        "status": "open",
        "ai_summary": "Water supply disrupted for 3 days, pump failure in Gulberg III.",
        "triaged_by": "rules",
        "triage_latency_ms": 320,
    },
    {
        "seed_key": "electricity-001",
        "text": "Bijli subah se nahi hai, transformer jal gaya hai. Ghar mein bache hain aur bahut garmi hai.",
        "location": "Model Town, Block E, Street 5",
        "category": "electricity",
        "priority": "high",
        "status": "in_progress",
        "ai_summary": "Transformer failure causing electricity outage in Model Town Block E.",
        "triaged_by": "rules",
        "triage_latency_ms": 410,
    },
    {
        "seed_key": "sanitation-001",
        "text": "Gutter overflow ho raha hai, sarak par gandgi phail gayi hai. Mahine bhar se koi sai nahin karta.",
        "location": "Johar Town, Sector B, Near Masjid",
        "category": "sanitation",
        "priority": "high",
        "status": "open",
        "ai_summary": "Sewage overflow on road for a month in Johar Town Sector B.",
        "triaged_by": "rules",
        "triage_latency_ms": 290,
    },
    {
        "seed_key": "roads-001",
        "text": "Sarak par bohot bade bade khaddey hain, gadiyan kharab ho rahi hain aur accidents ho rahe hain.",
        "location": "Ferozepur Road, Opposite General Hospital",
        "category": "roads",
        "priority": "high",
        "status": "resolved",
        "ai_summary": "Large potholes causing vehicle damage and accidents on Ferozepur Road.",
        "triaged_by": "rules",
        "triage_latency_ms": 370,
    },
    {
        "seed_key": "streetlights-001",
        "text": "Street lights kharab hain, raat ko andhra ho jata hai. Bachon ki safety ka masla hai.",
        "location": "DHA Phase 4, Block MM, Main Street",
        "category": "streetlights",
        "priority": "normal",
        "status": "open",
        "ai_summary": "Street lights out in DHA Phase 4, safety concern at night.",
        "triaged_by": "rules",
        "triage_latency_ms": 180,
    },
    {
        "seed_key": "water-002",
        "text": "Water supply pressure bohot kam hai, upar ke floors par pani nahi pahunchta.",
        "location": "Allama Iqbal Town, Ravi Block",
        "category": "water",
        "priority": "normal",
        "status": "open",
        "ai_summary": "Low water pressure prevents supply to upper floors in Iqbal Town.",
        "triaged_by": "rules",
        "triage_latency_ms": 250,
    },
    {
        "seed_key": "electricity-002",
        "text": "Load shedding schedule mein nahin tha, phir bhi 8 ghantay bijli band rahi.",
        "location": "Garden Town, Upper Mall Road",
        "category": "electricity",
        "priority": "normal",
        "status": "rejected",
        "ai_summary": "Unscheduled 8-hour power outage reported in Garden Town.",
        "triaged_by": "rules",
        "triage_latency_ms": 330,
    },
    {
        "seed_key": "sanitation-002",
        "text": "Dustbin nahi hai is area mein, log sarak ke kinare kachra pheink dete hain.",
        "location": "Shadman Colony, Near Park",
        "category": "sanitation",
        "priority": "low",
        "status": "open",
        "ai_summary": "No waste bin in Shadman Colony, residents dumping garbage on roadside.",
        "triaged_by": "rules",
        "triage_latency_ms": 210,
    },
    {
        "seed_key": "roads-002",
        "text": "Road construction incomplete chhod di gayi hai, barish mein pani jam jata hai.",
        "location": "Cavalry Ground, Sarwar Road",
        "category": "roads",
        "priority": "normal",
        "status": "in_progress",
        "ai_summary": "Incomplete road construction causing water logging in Cavalry Ground.",
        "triaged_by": "rules",
        "triage_latency_ms": 440,
    },
    {
        "seed_key": "streetlights-002",
        "text": "Poori street par sirf do lights kaam kar rahi hain, baki sab kharab hain.",
        "location": "Gulshan-e-Ravi, Block A",
        "category": "streetlights",
        "priority": "normal",
        "status": "open",
        "ai_summary": "Only 2 of several street lights functional in Gulshan-e-Ravi Block A.",
        "triaged_by": "rules",
        "triage_latency_ms": 195,
    },
    {
        "seed_key": "water-003",
        "text": "Paani ka rang peela aata hai, pene ke qabil nahi hai. Test karwana chahiye.",
        "location": "Iqbal Park Area, Near Railway Station",
        "category": "water",
        "priority": "high",
        "status": "open",
        "ai_summary": "Yellow discolored water reported near Railway Station, unsafe for drinking.",
        "triaged_by": "rules",
        "triage_latency_ms": 12,
    },
    {
        "seed_key": "electricity-003",
        "text": "Bijli meter kharab ho gaya hai, bill zyada aa raha hai lekin usage nahin hai.",
        "location": "Township Sector B3",
        "category": "electricity",
        "priority": "low",
        "status": "open",
        "ai_summary": "Faulty electricity meter causing inflated billing in Township B3.",
        "triaged_by": "rules",
        "triage_latency_ms": 8,
    },
    {
        "seed_key": "sanitation-003",
        "text": "Eid ke baad kachra uthaya nahin gaya, gandagi se beemar ho rahe hain log.",
        "location": "Samanabad, Near Ghee Mill",
        "category": "sanitation",
        "priority": "high",
        "status": "in_progress",
        "ai_summary": "Post-Eid waste not collected in Samanabad, health risk reported.",
        "triaged_by": "rules",
        "triage_latency_ms": 15,
    },
    {
        "seed_key": "roads-003",
        "text": "Sarak par speed breaker nahi hai school ke saamne, accidents ka darr hai.",
        "location": "Johar Town, School Zone, Block F",
        "category": "roads",
        "priority": "high",
        "status": "resolved",
        "ai_summary": "No speed breaker near school in Johar Town Block F, safety hazard.",
        "triaged_by": "rules",
        "triage_latency_ms": 11,
    },
    {
        "seed_key": "other-001",
        "text": "Masjid ke saamne footpath toot gayi hai, buzurg log girnay ke qareeb ho rahe hain.",
        "location": "Iqbal Town, Block P, Near Jamia Masjid",
        "category": "other",
        "priority": "normal",
        "status": "open",
        "ai_summary": "Broken footpath near mosque in Iqbal Town poses fall risk for elderly.",
        "triaged_by": "rules",
        "triage_latency_ms": 9,
    },
    {
        "seed_key": "water-004",
        "text": "Water leakage from main pipe on road, paani barbaad ho raha hai din bhar.",
        "location": "Cantt Area, Racecourse Road",
        "category": "water",
        "priority": "normal",
        "status": "resolved",
        "ai_summary": "Main water pipe leak on Racecourse Road, significant water wastage.",
        "triaged_by": "rules",
        "triage_latency_ms": 300,
    },
    {
        "seed_key": "electricity-004",
        "text": "Bijli ke khambay per wiring khuli padi hai, bacha haath laga sakta hai.",
        "location": "Wahdat Colony, Street 12",
        "category": "electricity",
        "priority": "high",
        "status": "in_progress",
        "ai_summary": "Exposed live wiring on electricity pole in Wahdat Colony, child safety risk.",
        "triaged_by": "rules",
        "triage_latency_ms": 380,
    },
    {
        "seed_key": "sanitation-004",
        "text": "Drain blocked hai, barish mein ghar mein pani aa jata hai. Ghar kharab ho raha hai.",
        "location": "Sabzazar Scheme, Block R",
        "category": "sanitation",
        "priority": "high",
        "status": "open",
        "ai_summary": "Blocked drain causing household flooding in Sabzazar Scheme Block R.",
        "triaged_by": "rules",
        "triage_latency_ms": 290,
    },
    {
        "seed_key": "roads-004",
        "text": "Road divider toot gaya hai, gadiyan galat side se aa rahi hain aur accidents ho rahe hain.",
        "location": "Mall Road, Near Lahore Museum",
        "category": "roads",
        "priority": "high",
        "status": "open",
        "ai_summary": "Damaged road divider near Lahore Museum causing wrong-way driving.",
        "triaged_by": "rules",
        "triage_latency_ms": 420,
    },
    {
        "seed_key": "streetlights-003",
        "text": "Park mein raat ko lights nahi hain, mahila hazraat park mein janey se darte hain.",
        "location": "Jinnah Park, Main Gate Area",
        "category": "streetlights",
        "priority": "high",
        "status": "open",
        "ai_summary": "No lighting in Jinnah Park at night, women afraid to use park.",
        "triaged_by": "rules",
        "triage_latency_ms": 275,
    },
    {
        "seed_key": "water-005",
        "text": "Water connection cut ho gaya hai bina notice ke, bill bhi paid hai.",
        "location": "Gulistan Colony, Near Chowk",
        "category": "water",
        "priority": "high",
        "status": "resolved",
        "ai_summary": "Water connection cut without notice despite paid bills in Gulistan Colony.",
        "triaged_by": "rules:fallback",
        "triage_latency_ms": 5500,
    },
    {
        "seed_key": "electricity-005",
        "text": "Naye connection ke liye apply kiya, teen mahine ho gaye koi jawab nahi.",
        "location": "LESCO Office, Gulberg Branch",
        "category": "electricity",
        "priority": "low",
        "status": "open",
        "ai_summary": "New electricity connection application pending 3 months at Gulberg LESCO.",
        "triaged_by": "rules:fallback",
        "triage_latency_ms": 5100,
    },
    {
        "seed_key": "sanitation-005",
        "text": "Sweeper nahi aata iss gali mein, akhri baar kab aaya pata nahi.",
        "location": "Badami Bagh, Street 7",
        "category": "sanitation",
        "priority": "normal",
        "status": "open",
        "ai_summary": "Street sweeper absent from Badami Bagh Street 7, duration unknown.",
        "triaged_by": "rules",
        "triage_latency_ms": 210,
    },
    {
        "seed_key": "roads-005",
        "text": "Bridge par railing toot gayi hai, khatra hai motorcycle wallon ko.",
        "location": "Shahdara Bridge, Left Side",
        "category": "roads",
        "priority": "high",
        "status": "open",
        "ai_summary": "Broken bridge railing on Shahdara Bridge left side, motorcycle hazard.",
        "triaged_by": "rules",
        "triage_latency_ms": 345,
    },
    {
        "seed_key": "other-002",
        "text": "Neighborhood notice board toot gaya hai, log community notices nahin padh paate.",
        "location": "Cavalry Ground, Sector 4 Community Center",
        "category": "other",
        "priority": "low",
        "status": "rejected",
        "ai_summary": "Damaged community notice board in Cavalry Ground Sector 4.",
        "triaged_by": "rules",
        "triage_latency_ms": 165,
    },
    {
        "seed_key": "water-006",
        "text": "Water tank overflow ho raha hai, paani barbaad ho raha hai pichle hafte se.",
        "location": "Manga Mandi Road, Near Water Tower",
        "category": "water",
        "priority": "normal",
        "status": "in_progress",
        "ai_summary": "Overflowing water tank near Manga Mandi Water Tower wasting supply.",
        "triaged_by": "rules",
        "triage_latency_ms": 280,
    },
    {
        "seed_key": "electricity-006",
        "text": "Voltage fluctuation se ghar ke appliances kharab ho rahe hain, stabilizer bhi kaam nahi kar raha.",
        "location": "Gulshan-e-Iqbal, Block 9",
        "category": "electricity",
        "priority": "normal",
        "status": "open",
        "ai_summary": "Voltage fluctuations damaging home appliances in Gulshan-e-Iqbal Block 9.",
        "triaged_by": "rules",
        "triage_latency_ms": 310,
    },
    {
        "seed_key": "sanitation-006",
        "text": "Nala safai nahin hui is saal, barish aa jaey to flooding ho jata hai poore mohalle mein.",
        "location": "Ravi Road, Near Old Bridge",
        "category": "sanitation",
        "priority": "high",
        "status": "open",
        "ai_summary": "Storm drain not cleaned this year, flood risk for entire neighborhood.",
        "triaged_by": "rules",
        "triage_latency_ms": 395,
    },
    {
        "seed_key": "roads-006",
        "text": "Sarak par marking band ho gayi hai, traffic confusion ho raha hai crossings par.",
        "location": "Allama Iqbal Road, Main Intersection",
        "category": "roads",
        "priority": "normal",
        "status": "open",
        "ai_summary": "Faded road markings causing traffic confusion at Allama Iqbal Road intersection.",
        "triaged_by": "rules",
        "triage_latency_ms": 255,
    },
    {
        "seed_key": "streetlights-004",
        "text": "Raat bhar lights jalti rehti hain din mein bhi band nahi hoti, bijli barbaad ho rahi hai.",
        "location": "Anarkali Bazaar, Food Street Area",
        "category": "streetlights",
        "priority": "low",
        "status": "resolved",
        "ai_summary": "Street lights not turning off during daytime in Anarkali Bazaar area.",
        "triaged_by": "rules",
        "triage_latency_ms": 170,
    },
    {
        "seed_key": "other-003",
        "text": "Public toilet band hai government park mein, koi maintenance nahin hai.",
        "location": "Lawrence Garden, Near Fountain",
        "category": "other",
        "priority": "normal",
        "status": "open",
        "ai_summary": "Public toilet closed in Lawrence Garden, no maintenance staff present.",
        "triaged_by": "rules",
        "triage_latency_ms": 230,
    },
    {
        "seed_key": "water-007",
        "text": "Boring ka paani kharab hai is colony mein, municipality supply par depend karna padta hai jo bhi nahi aati.",
        "location": "Green Town, Block A, Near School",
        "category": "water",
        "priority": "high",
        "status": "open",
        "ai_summary": "Borehole water contaminated in Green Town, no alternative municipal supply.",
        "triaged_by": "rules",
        "triage_latency_ms": 360,
    },
]


async def run_seed() -> None:
    """Seed the database idempotently with >=30 complaints."""
    # From the environment, or .env via the app settings; never a hardcoded default.
    from app.core.config import Settings

    db_url = os.getenv("DATABASE_URL") or str(Settings().database_url)
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Import here to avoid circular imports at module level

    from app.models.complaint import Complaint

    inserted = 0
    skipped = 0

    async with session_factory() as session:
        for data in COMPLAINTS:
            deterministic_id = seed_uuid(data["seed_key"])

            # Check if already seeded (idempotency check)
            existing = await session.get(Complaint, deterministic_id)
            if existing is not None:
                skipped += 1
                continue

            complaint = Complaint(
                id=deterministic_id,
                text=data["text"],
                location=data["location"],
                category=data["category"],
                priority=data["priority"],
                status=data["status"],
                ai_summary=data.get("ai_summary"),
                triaged_by=data.get("triaged_by"),
                triage_latency_ms=data.get("triage_latency_ms"),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            session.add(complaint)
            inserted += 1

        await session.commit()

    await engine.dispose()
    print(f"Seed complete: {inserted} inserted, {skipped} skipped (already existed).")
    print(f"Total complaints in seed data: {len(COMPLAINTS)}")


if __name__ == "__main__":
    asyncio.run(run_seed())
