#!/usr/bin/env python3
"""
PMG Billboard Catalog - Music Knowledge Injection System
Injects billboard chart data, frequency/harmonic analysis, hit record patterns
into the Omni-Studio database for AI agents to query.
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import random

BASE = Path(__file__).parent
DB_PATH = BASE / "data" / "dashboard.db"
KNOWLEDGE_DB = BASE / "data" / "music_knowledge.db"

# =============================================================================
# BILLBOARD CHART KNOWLEDGE BASE
# =============================================================================

BILLBOARD_HOT_100_ARCHETYPES = [
    # (decade, genre, typical_bpm_range, common_keys, song_structure, production_traits)
    ("1960s", "Motown/Soul", (100, 120), ["C", "F", "G", "Bb", "Eb"], "AABA", 
     ["horn sections", "tight rhythm section", "call-response vocals", "modulation up half-step"]),
    ("1970s", "Disco", (118, 130), ["Am", "Dm", "Em", "Bm", "F#m"], "Verse-Chorus-Verse-Chorus-Bridge-Chorus",
     ["four-on-the-floor", "string orchestration", "syncopated bass", "breakdown bridge"]),
    ("1980s", "Synth-Pop/New Wave", (110, 132), ["Cm", "Gm", "Dm", "Am", "Fm"], "Verse-Chorus-Verse-Chorus-Solo-Chorus",
     ["dx7/bass synth", "gated reverb drums", "arpeggiated synths", "key change final chorus"]),
    ("1990s", "Grunge/Alternative", (80, 140), ["E", "A", "D", "G", "C"], "Verse-Chorus-Verse-Chorus-Bridge-Chorus",
     ["heavy distortion", "quiet-loud dynamics", "drop-D tuning", "feedback"]),
    ("1990s", "Hip-Hop/R&B", (85, 105), ["C#m", "F#m", "Bm", "G#m", "Ebm"], "Verse-Chorus-Verse-Chorus-Bridge-Chorus",
     ["sample-based", "swing quantization", "sub-bass", "vocal harmonies"]),
    ("2000s", "Pop-Punk/Emo", (150, 180), ["E", "B", "G#m", "C#m", "A"], "Verse-Chorus-Verse-Chorus-Breakdown-Chorus",
     ["power chords", "palm muting", "double-time drums", "gang vocals"]),
    ("2000s", "Crunk/Snap", (70, 90), ["F#m", "C#m", "G#m", "Bm"], "Verse-Chorus-Verse-Chorus",
     ["808 kicks", "hand claps", "simple synth melodies", "chant hooks"]),
    ("2010s", "EDM/Pop", (126, 128), ["Am", "C", "F", "G", "Em"], "Verse-Build-Drop-Verse-Build-Drop-Bridge-Drop",
     ["sidechain compression", "supersaw leads", "vocal chops", "risers/downers"]),
    ("2010s", "Trap", (130, 160), ["Dm", "Gm", "Cm", "Fm", "Bbm"], "Verse-Chorus-Verse-Chorus",
     ["rolling hi-hats", "808 glides", "half-time feel", "triplet flows"]),
    ("2020s", "Hyperpop/Glitch", (140, 180), ["C#m", "F#m", "G#m", "A", "E"], "A-B-A-B-C-B",
     ["pitch-shifted vocals", "glitch percussion", "genre-blending", "maximalist production"]),
    ("2020s", "Afrobeats/Amapiano", (110, 120), ["Am", "Em", "Bm", "F#m", "C#m"], "Verse-Chorus-Verse-Chorus",
     ["log drums", "3-2 clave", "percussive piano", "call-response"]),
]

# Frequency/Harmonic Analysis for Hit Records
HIT_RECORD_FREQUENCY_PROFILES = {
    "pop": {
        "sub_bass": (20, 60, "Fundamental weight, 808 subs"),
        "bass": (60, 250, "Bass guitar/synth body, kick drum fundamental"),
        "low_mid": (250, 500, "Vocal warmth, snare body, mud zone"),
        "mid": (500, 2000, "Vocal presence, guitar attack, snare crack"),
        "upper_mid": (2000, 4000, "Vocal intelligibility, cymbal attack, ear sensitivity"),
        "presence": (4000, 6000, "Vocal air, drum attack, presence"),
        "brilliance": (6000, 20000, "Air, shimmer, cymbal decay"),
    },
    "hip_hop": {
        "sub_bass": (20, 60, "Heavy 808 subs, below 40Hz for club systems"),
        "bass": (60, 200, "808 body, kick punch"),
        "low_mid": (200, 500, "Sample warmth, vocal low-end"),
        "mid": (500, 2000, "Vocal clarity, snare snap"),
        "upper_mid": (2000, 4000, "Hi-hat articulation, vocal bite"),
        "presence": (4000, 8000, "Hi-hat sizzle, vocal air"),
        "brilliance": (8000, 20000, "Cymbal shimmer, sparkle"),
    },
    "edm": {
        "sub_bass": (20, 50, "Clean sine sub, mono below 100Hz"),
        "bass": (50, 200, "Reese bass, supersaw harmonics"),
        "low_mid": (200, 400, "Pad warmth, vocal body"),
        "mid": (400, 2000, "Lead synth presence, vocal"),
        "upper_mid": (2000, 5000, "Pluck attack, white noise risers"),
        "presence": (5000, 10000, "Supersaw brightness, vocal chop articulation"),
        "brilliance": (10000, 20000, "Air, reverb tails, excitement"),
    },
}

# Harmonic relationships that create "hit" feel
HARMONIC_HIT_PATTERNS = {
    "four_chord_loop": ["I", "V", "vi", "IV"],  # Pop standard
    "ii_V_I": ["ii", "V", "I"],  # Jazz/pop resolution
    "andalusian": ["iv", "III", "II", "I"],  # Flamenco/Latin pop
    "axis_progression": ["IV", "V", "iii", "vi"],  # Japanese pop/anime
    "blues": ["I7", "IV7", "V7"],  # Foundation of rock/R&B
    "pop_punk": ["I", "V", "vi", "IV"],  # Same as four_chord but faster
    "trap_minor": ["i", "VII", "VI", "V7"],  # Minor key trap
    "house": ["i", "iv", "i", "VII"],  # Minor house loop
}

# Vibration/Resonance concepts for production
RESONANCE_CONCEPTS = {
    "schumann_resonance": 7.83,  # Earth's electromagnetic resonance
    "solfeggio_frequencies": {
        "UT": 396,   # Liberating guilt/fear
        "RE": 417,   # Undoing situations
        "MI": 528,   # Transformation/DNA repair (love frequency)
        "FA": 639,   # Relationships/connection
        "SOL": 741,  # Expression/solutions
        "LA": 852,   # Intuition/awakening
    },
    "a432_vs_a440": {
        "A432": "Claimed more natural, resonant with nature",
        "A440": "International standard since 1939",
        "difference": "~32 cents (1/3 semitone)",
    },
    "harmonic_series": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],  # Overtones
    "golden_ratio_tempo": 120 / 1.618,  # ~74 BPM - "universal" groove
}

# =============================================================================
# DATABASE SETUP
# =============================================================================

def init_knowledge_db():
    """Create music knowledge database"""
    KNOWLEDGE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(KNOWLEDGE_DB))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS billboard_archetypes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decade TEXT, genre TEXT, bpm_min INTEGER, bpm_max INTEGER,
            common_keys TEXT, song_structure TEXT, production_traits TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS frequency_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            genre TEXT, band_name TEXT, freq_low INTEGER, freq_high INTEGER,
            description TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS harmonic_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_name TEXT, chords TEXT, genre_affinity TEXT,
            emotional_impact TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS resonance_concepts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_name TEXT, value REAL, description TEXT,
            category TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        
        CREATE TABLE IF NOT EXISTS hit_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, artist TEXT, year INTEGER, peak_position INTEGER,
            key_signature TEXT, tempo REAL, structure TEXT,
            frequency_profile TEXT, harmonic_pattern TEXT,
            production_notes TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    print(f"✅ Knowledge DB initialized: {KNOWLEDGE_DB}")

def populate_knowledge_base():
    """Inject all music knowledge into database"""
    conn = sqlite3.connect(str(KNOWLEDGE_DB))
    cursor = conn.cursor()
    
    # Billboard archetypes
    for archetype in BILLBOARD_HOT_100_ARCHETYPES:
        decade, genre, bpm_range, keys, structure, traits = archetype
        cursor.execute("""
            INSERT OR IGNORE INTO billboard_archetypes 
            (decade, genre, bpm_min, bpm_max, common_keys, song_structure, production_traits)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (decade, genre, bpm_range[0], bpm_range[1], json.dumps(keys), structure, json.dumps(traits)))
    
    # Frequency profiles
    for genre, bands in HIT_RECORD_FREQUENCY_PROFILES.items():
        for band_name, (low, high, desc) in bands.items():
            cursor.execute("""
                INSERT OR IGNORE INTO frequency_profiles
                (genre, band_name, freq_low, freq_high, description)
                VALUES (?, ?, ?, ?, ?)
            """, (genre, band_name, low, high, desc))
    
    # Harmonic patterns
    for pattern_name, chords in HARMONIC_HIT_PATTERNS.items():
        genre_affinity = {
            "four_chord_loop": "pop, country, folk",
            "ii_V_I": "jazz, pop, r&b",
            "andalusian": "latin, flamenco, pop",
            "axis_progression": "j-pop, anime, video game",
            "blues": "blues, rock, r&b",
            "pop_punk": "pop-punk, emo, alternative",
            "trap_minor": "trap, drill, hip-hop",
            "house": "house, techno, edm",
        }.get(pattern_name, "general")
        
        cursor.execute("""
            INSERT OR IGNORE INTO harmonic_patterns
            (pattern_name, chords, genre_affinity, emotional_impact)
            VALUES (?, ?, ?, ?)
        """, (pattern_name, json.dumps(chords), genre_affinity, 
              "Resolution/tension cycle that drives engagement"))
    
    # Resonance concepts
    cursor.execute("""
        INSERT OR IGNORE INTO resonance_concepts (concept_name, value, description, category)
        VALUES (?, ?, ?, ?)
    """, ("schumann_resonance", 7.83, "Earth's electromagnetic resonance frequency", "planetary"))
    
    for name, freq in RESONANCE_CONCEPTS["solfeggio_frequencies"].items():
        desc = {
            "UT": "Liberating guilt and fear",
            "RE": "Undoing situations and facilitating change",
            "MI": "Transformation and miracles (DNA repair - love frequency)",
            "FA": "Connecting/relationships",
            "SOL": "Expression and solutions",
            "LA": "Awakening intuition",
        }[name]
        cursor.execute("""
            INSERT OR IGNORE INTO resonance_concepts (concept_name, value, description, category)
            VALUES (?, ?, ?, ?)
        """, (f"solfeggio_{name}", freq, desc, "solfeggio"))
    
    # A432 vs A440
    cursor.execute("""
        INSERT OR IGNORE INTO resonance_concepts (concept_name, value, description, category)
        VALUES (?, ?, ?, ?)
    """, ("a432_tuning", 432, "Alternative tuning claimed to be more natural/resonant", "tuning_standard"))
    
    cursor.execute("""
        INSERT OR IGNORE INTO resonance_concepts (concept_name, value, description, category)
        VALUES (?, ?, ?, ?)
    """, ("a440_tuning", 440, "International concert pitch standard since 1939", "tuning_standard"))
    
    # Golden ratio tempo
    cursor.execute("""
        INSERT OR IGNORE INTO resonance_concepts (concept_name, value, description, category)
        VALUES (?, ?, ?, ?)
    """, ("golden_ratio_tempo", 120/1.618, "Tempo derived from golden ratio (120/φ)", "mathematical"))
    
    # Harmonic series
    for i, harmonic in enumerate(RESONANCE_CONCEPTS["harmonic_series"]):
        cursor.execute("""
            INSERT OR IGNORE INTO resonance_concepts (concept_name, value, description, category)
            VALUES (?, ?, ?, ?)
        """, (f"harmonic_{harmonic}", harmonic, f"{harmonic}x fundamental frequency", "harmonic_series"))
    
    conn.commit()
    conn.close()
    print("✅ Knowledge base populated")

# =============================================================================
# INTEGRATION WITH MAIN DASHBOARD DB
# =============================================================================

async def add_knowledge_to_dashboard_db():
    """Add music knowledge tables to main dashboard.db"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS music_knowledge_billboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decade TEXT, genre TEXT, bpm_min INTEGER, bpm_max INTEGER,
            common_keys TEXT, song_structure TEXT, production_traits TEXT
        );
        
        CREATE TABLE IF NOT EXISTS music_knowledge_frequency (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            genre TEXT, band TEXT, freq_low INTEGER, freq_high INTEGER, description TEXT
        );
        
        CREATE TABLE IF NOT EXISTS music_knowledge_harmonic (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_name TEXT, chords TEXT, genre_affinity TEXT, emotional_impact TEXT
        );
        
        CREATE TABLE IF NOT EXISTS music_knowledge_resonance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept TEXT, value REAL, description TEXT, category TEXT
        );
    """)
    conn.commit()
    
    # Copy from knowledge DB
    kconn = sqlite3.connect(str(KNOWLEDGE_DB))
    
    for row in kconn.execute("SELECT * FROM billboard_archetypes"):
        # row has 8 columns (id, decade, genre, bpm_min, bpm_max, common_keys, song_structure, production_traits, created_at)
        # target has 7 columns (id auto, decade, genre, bpm_min, bpm_max, common_keys, song_structure, production_traits)
        conn.execute("INSERT OR IGNORE INTO music_knowledge_billboard (decade, genre, bpm_min, bpm_max, common_keys, song_structure, production_traits) VALUES (?,?,?,?,?,?,?)", row[1:8])
    
    for row in kconn.execute("SELECT * FROM frequency_profiles"):
        # row has 6 columns (id, genre, band_name, freq_low, freq_high, description, created_at)
        # target has 5 columns (id auto, genre, band, freq_low, freq_high, description)
        conn.execute("INSERT OR IGNORE INTO music_knowledge_frequency (genre, band, freq_low, freq_high, description) VALUES (?,?,?,?,?)", row[1:6])
    
    for row in kconn.execute("SELECT * FROM harmonic_patterns"):
        # row has 5 columns (id, pattern_name, chords, genre_affinity, emotional_impact, created_at)
        conn.execute("INSERT OR IGNORE INTO music_knowledge_harmonic (pattern_name, chords, genre_affinity, emotional_impact) VALUES (?,?,?,?)", row[1:5])
    
    for row in kconn.execute("SELECT * FROM resonance_concepts"):
        # row has 5 columns (id, concept_name, value, description, category, created_at)
        conn.execute("INSERT OR IGNORE INTO music_knowledge_resonance (concept, value, description, category) VALUES (?,?,?,?)", row[1:5])
    
    conn.commit()
    kconn.close()
    conn.close()
    print("✅ Knowledge synced to dashboard.db")

# =============================================================================
# API FOR AGENTS TO QUERY
# =============================================================================

async def get_billboard_archetype_for_tempo(tempo: float, genre: str = ""):
    """Get billboard archetype matching tempo/genre"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM music_knowledge_billboard WHERE bpm_min <= ? AND bpm_max >= ?"
    params = [tempo, tempo]
    if genre:
        query += " AND genre LIKE ?"
        params.append(f"%{genre}%")
    
    rows = cursor.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

async def get_frequency_profile(genre: str):
    """Get frequency bands for a genre"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM music_knowledge_frequency WHERE genre = ?", (genre,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

async def get_harmonic_patterns_for_genre(genre: str):
    """Get chord progressions that work for a genre"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM music_knowledge_harmonic WHERE genre_affinity LIKE ?", (f"%{genre}%",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

async def get_resonance_concepts(category: str = ""):
    """Get vibration/resonance concepts"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    if category:
        rows = conn.execute("SELECT * FROM music_knowledge_resonance WHERE category = ?", (category,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM music_knowledge_resonance").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# =============================================================================
# MAIN
# =============================================================================

async def main():
    print("🎵 PMG BILLBOARD - Music Knowledge Injection System")
    print("=" * 60)
    
    init_knowledge_db()
    populate_knowledge_base()
    await add_knowledge_to_dashboard_db()
    
    # Test queries
    print("\n🔍 Testing agent queries...")
    
    # Test 1: Find archetype for 128 BPM EDM
    results = await get_billboard_archetype_for_tempo(128, "edm")
    print(f"\n128 BPM EDM archetypes: {len(results)}")
    for r in results:
        print(f"  → {r['decade']} {r['genre']}: {r['song_structure']}")
    
    # Test 2: Frequency profile for trap
    freq = await get_frequency_profile("hip_hop")
    print(f"\nHip-hop frequency bands: {len(freq)}")
    for f in freq:
        print(f"  → {f['band']}: {f['freq_low']}-{f['freq_high']}Hz - {f['description']}")
    
    # Test 3: Harmonic patterns for trap
    patterns = await get_harmonic_patterns_for_genre("trap")
    print(f"\nTrap harmonic patterns: {len(patterns)}")
    for p in patterns:
        print(f"  → {p['pattern_name']}: {json.loads(p['chords'])}")
    
    # Test 4: Resonance concepts
    resonance = await get_resonance_concepts("solfeggio")
    print(f"\nSolfeggio frequencies: {len(resonance)}")
    for r in resonance:
        print(f"  → {r['concept']}: {r['value']}Hz - {r['description']}")
    
    print("\n✅ Music Knowledge Injection Complete!")
    print(f"📊 Knowledge DB: {KNOWLEDGE_DB}")
    print(f"📊 Dashboard DB: {DB_PATH}")

if __name__ == "__main__":
    asyncio.run(main())
