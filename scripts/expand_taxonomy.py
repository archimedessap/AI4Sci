#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_JSON = ROOT / "web" / "data" / "base.json"


@dataclass(frozen=True)
class NodeSpec:
    id: str
    name: str
    parent_id: str | None
    order: int
    description: str | None = None
    concept_name: str | None = None  # OpenAlex concept display_name; id will be filled by update script.
    concept_id: str | None = None  # Optional stable OpenAlex concept id (C123...).


def node_obj(spec: NodeSpec, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = dict(existing or {})
    out["id"] = spec.id
    out["name"] = spec.name
    out["parentId"] = spec.parent_id
    out["order"] = spec.order
    if spec.description:
        out["description"] = spec.description
    if spec.concept_id or spec.concept_name:
        out.setdefault("openalex", {}).setdefault("concept", {})
    if spec.concept_id:
        out["openalex"]["concept"]["id"] = spec.concept_id
    if spec.concept_name:
        out["openalex"]["concept"]["name"] = spec.concept_name
    return out


def main() -> int:
    if not BASE_JSON.exists():
        raise SystemExit(f"Base not found: {BASE_JSON}")

    base = json.loads(BASE_JSON.read_text("utf-8"))
    nodes: dict[str, dict[str, Any]] = base.get("nodes") or {}

    # --- Physics ---
    physics_new = [
        NodeSpec(
            id="physics_foundations",
            name="Foundations & Cosmology",
            parent_id="physics",
            order=11,
            description="QG / HEP / Cosmology (fundamental laws and early universe).",
        ),
        NodeSpec(
            id="physics_matter",
            name="Matter & Statistical Physics",
            parent_id="physics",
            order=12,
            description="Condensed matter, statistical mechanics, soft matter.",
        ),
        NodeSpec(
            id="physics_dynamics",
            name="Dynamics",
            parent_id="physics",
            order=13,
            description="Fluids and dynamical systems.",
        ),
        NodeSpec(
            id="physics_quantumtech",
            name="Quantum Information",
            parent_id="physics",
            order=14,
            description="Quantum information and quantum technologies.",
        ),
        NodeSpec(
            id="physics_optics",
            name="Optics & Photonics",
            parent_id="physics",
            order=15,
            description="Optics/photonics and related measurements.",
        ),
        NodeSpec(
            id="physics_astro",
            name="Astronomy & Space",
            parent_id="physics",
            order=16,
            description="Astronomy, astrophysics, planets, and space weather.",
        ),
        NodeSpec(
            id="physics_statmech",
            name="Statistical Mechanics",
            parent_id="physics_matter",
            order=121,
            concept_name="Statistical mechanics",
        ),
        NodeSpec(
            id="physics_softmatter",
            name="Soft Matter",
            parent_id="physics_matter",
            order=122,
            concept_name="Soft matter",
        ),
        NodeSpec(
            id="physics_fluid",
            name="Fluid Dynamics",
            parent_id="physics_dynamics",
            order=131,
            concept_name="Fluid dynamics",
        ),
        NodeSpec(
            id="physics_qinfo",
            name="Quantum Information",
            parent_id="physics_quantumtech",
            order=141,
            concept_name="Quantum information",
        ),
        NodeSpec(
            id="physics_photonics",
            name="Photonics",
            parent_id="physics_optics",
            order=151,
            concept_name="Photonics",
        ),
        NodeSpec(
            id="physics_atomic",
            name="Atomic Physics",
            parent_id="physics_optics",
            order=152,
            concept_name="Atomic physics",
            concept_id="C184779094",
        ),
        NodeSpec(
            id="physics_nuclear",
            name="Nuclear Physics",
            parent_id="physics_foundations",
            order=15,
            concept_name="Nuclear physics",
            concept_id="C185544564",
        ),
        NodeSpec(
            id="physics_hep",
            name="Particle Physics",
            parent_id="physics_foundations",
            order=12,
            concept_name="Particle physics",
            concept_id="C109214941",
        ),
        NodeSpec(
            id="physics_astronomy",
            name="Astronomy",
            parent_id="physics_astro",
            order=161,
            concept_name="Astronomy",
            concept_id="C1276947",
        ),
        NodeSpec(
            id="physics_astrophysics",
            name="Astrophysics",
            parent_id="physics_astro",
            order=162,
            concept_name="Astrophysics",
            concept_id="C44870925",
        ),
        NodeSpec(
            id="physics_planetary",
            name="Planetary Science",
            parent_id="physics_astro",
            order=163,
            concept_name="Planetary science",
            concept_id="C152551177",
        ),
        NodeSpec(
            id="physics_exoplanet",
            name="Exoplanets",
            parent_id="physics_astro",
            order=164,
            concept_name="Exoplanet",
            concept_id="C163479331",
        ),
        NodeSpec(
            id="physics_solar",
            name="Solar Physics",
            parent_id="physics_astro",
            order=165,
            concept_name="Solar physics",
            concept_id="C183682340",
        ),
        NodeSpec(
            id="physics_space_weather",
            name="Space Weather",
            parent_id="physics_astro",
            order=166,
            concept_name="Space weather",
            concept_id="C151325931",
        ),
        NodeSpec(
            id="physics_astrobiology",
            name="Astrobiology",
            parent_id="physics_astro",
            order=167,
            concept_name="Astrobiology",
            concept_id="C87355193",
        ),
    ]

    # Move existing physics leaves under the new mid-level nodes (keep their scores).
    physics_moves = {
        "physics_qg": "physics_foundations",
        "physics_hep": "physics_foundations",
        "physics_cosmo": "physics_foundations",
        "physics_cmp": "physics_matter",
    }

    # --- Chemistry & Materials ---
    chem_new = [
        NodeSpec(
            id="chemistry",
            name="Chemistry",
            parent_id="chem_mat",
            order=21,
            description="Molecules, reactions, and quantum/physical chemistry.",
        ),
        NodeSpec(
            id="materials",
            name="Materials",
            parent_id="chem_mat",
            order=22,
            description="Materials discovery, properties, and synthesis.",
        ),
        NodeSpec(
            id="chem_org",
            name="Organic Chemistry",
            parent_id="chemistry",
            order=211,
            concept_name="Organic chemistry",
        ),
        NodeSpec(
            id="chem_inorg",
            name="Inorganic Chemistry",
            parent_id="chemistry",
            order=212,
            concept_name="Inorganic chemistry",
        ),
        NodeSpec(
            id="chem_physchem",
            name="Physical Chemistry",
            parent_id="chemistry",
            order=213,
            concept_name="Physical chemistry",
        ),
        NodeSpec(
            id="chem_electro",
            name="Electrochemistry",
            parent_id="chemistry",
            order=214,
            concept_name="Electrochemistry",
        ),
        NodeSpec(
            id="chem_polymer",
            name="Polymer Chemistry",
            parent_id="chemistry",
            order=215,
            concept_name="Polymer chemistry",
        ),
        NodeSpec(
            id="chem_computational",
            name="Computational Chemistry",
            parent_id="chemistry",
            order=216,
            concept_name="Computational chemistry",
            concept_id="C147597530",
        ),
        NodeSpec(
            id="chem_kinetics",
            name="Chemical Kinetics",
            parent_id="chemistry",
            order=217,
            concept_name="Chemical kinetics",
            concept_id="C36663273",
        ),
        NodeSpec(
            id="chem_medicinal",
            name="Medicinal Chemistry",
            parent_id="chemistry",
            order=218,
            concept_name="Medicinal chemistry",
            concept_id="C155647269",
        ),
        NodeSpec(
            id="chem_synthesis",
            name="Chemical Synthesis",
            parent_id="chemistry",
            order=219,
            concept_name="Chemical synthesis",
            concept_id="C114373084",
        ),
        NodeSpec(
            id="mat_battery",
            name="Batteries & Energy Storage",
            parent_id="materials",
            order=221,
            concept_name="Battery (electricity)",
        ),
        NodeSpec(
            id="mat_semiconductor",
            name="Semiconductors",
            parent_id="materials",
            order=222,
            concept_name="Semiconductor",
        ),
        NodeSpec(
            id="mat_nano",
            name="Nanomaterials",
            parent_id="materials",
            order=223,
            concept_name="Nanomaterials",
        ),
        NodeSpec(
            id="mat_nanotech",
            name="Nanotechnology",
            parent_id="materials",
            order=224,
            concept_name="Nanotechnology",
        ),
    ]

    chem_moves = {
        "chem_qc": "chemistry",
        "chem_catalysis": "chemistry",
        "mat_sci": "materials",
    }

    # --- Life Sciences & Medicine ---
    life_new = [
        NodeSpec(
            id="bio_molecular",
            name="Molecular & Cellular",
            parent_id="life",
            order=31,
            description="Proteins, genomes, cells, and molecular systems.",
        ),
        NodeSpec(
            id="bio_neuroscience",
            name="Neuroscience",
            parent_id="life",
            order=32,
            description="Brain, cognition, and neural systems.",
        ),
        NodeSpec(
            id="bio_health",
            name="Medicine & Health",
            parent_id="life",
            order=33,
            description="Clinical and translational science, population health.",
        ),
        NodeSpec(
            id="bio_structural",
            name="Structural Biology",
            parent_id="bio_molecular",
            order=311,
            concept_name="Structural biology",
        ),
        NodeSpec(
            id="bio_singlecell",
            name="Single-Cell Analysis",
            parent_id="bio_molecular",
            order=312,
            concept_name="Single-cell analysis",
        ),
        NodeSpec(
            id="bio_microbiome",
            name="Microbiome",
            parent_id="bio_molecular",
            order=313,
            concept_name="Microbiome",
        ),
        NodeSpec(
            id="bio_immunology",
            name="Immunology",
            parent_id="bio_molecular",
            order=314,
            concept_name="Immunology",
        ),
        NodeSpec(
            id="bio_systems",
            name="Systems Biology",
            parent_id="bio_molecular",
            order=315,
            concept_name="Systems biology",
        ),
        NodeSpec(
            id="bio_metabolomics",
            name="Metabolomics",
            parent_id="bio_molecular",
            order=316,
            concept_name="Metabolomics",
        ),
        NodeSpec(
            id="bio_proteomics",
            name="Proteomics",
            parent_id="bio_molecular",
            order=317,
            concept_name="Proteomics",
            concept_id="C46111723",
        ),
        NodeSpec(
            id="bio_metagenomics",
            name="Metagenomics",
            parent_id="bio_molecular",
            order=318,
            concept_name="Metagenomics",
            concept_id="C15151743",
        ),
        NodeSpec(
            id="med_drug",
            name="Drug Discovery",
            parent_id="bio_health",
            order=331,
            concept_name="Drug discovery",
        ),
        NodeSpec(
            id="med_epi",
            name="Epidemiology",
            parent_id="bio_health",
            order=332,
            concept_name="Epidemiology",
        ),
        NodeSpec(
            id="med_oncology",
            name="Oncology",
            parent_id="bio_health",
            order=333,
            concept_name="Oncology",
            concept_id="C143998085",
        ),
        NodeSpec(
            id="med_clinical_trial",
            name="Clinical Trials",
            parent_id="bio_health",
            order=334,
            concept_name="Clinical trial",
            concept_id="C535046627",
        ),
        NodeSpec(
            id="med_imaging",
            name="Medical Imaging",
            parent_id="bio_health",
            order=335,
            concept_name="Medical imaging",
            concept_id="C31601959",
        ),
        NodeSpec(
            id="med_pathology",
            name="Pathology",
            parent_id="bio_health",
            order=336,
            concept_name="Pathology",
            concept_id="C142724271",
        ),
    ]

    life_moves = {
        "bio_protein": "bio_molecular",
        "bio_genomics": "bio_molecular",
        "bio_neuro": "bio_neuroscience",
        "medicine": "bio_health",
    }

    # --- Earth Systems ---
    earth_new = [
        NodeSpec(
            id="earth_climate",
            name="Climate & Atmosphere",
            parent_id="earth",
            order=41,
            description="Climate dynamics, weather, and atmospheric processes.",
        ),
        NodeSpec(
            id="earth_geoscience",
            name="Geoscience",
            parent_id="earth",
            order=42,
            description="Geophysics, geology, and solid Earth.",
        ),
        NodeSpec(
            id="earth_hydrosphere",
            name="Hydrosphere",
            parent_id="earth",
            order=43,
            description="Ocean and hydrological systems.",
        ),
        NodeSpec(
            id="earth_ecosystems",
            name="Ecosystems & Biodiversity",
            parent_id="earth",
            order=44,
            description="Ecology, biodiversity, and coupled biosphere dynamics.",
        ),
        NodeSpec(
            id="earth_observation",
            name="Earth Observation",
            parent_id="earth",
            order=45,
            description="Remote sensing and observation pipelines.",
        ),
        NodeSpec(
            id="earth_meteorology",
            name="Meteorology",
            parent_id="earth_climate",
            order=411,
            concept_name="Meteorology",
        ),
        NodeSpec(
            id="earth_cryosphere",
            name="Cryosphere",
            parent_id="earth_climate",
            order=412,
            concept_name="Cryosphere",
            concept_id="C197435368",
        ),
        NodeSpec(
            id="earth_air_pollution",
            name="Air Pollution",
            parent_id="earth_climate",
            order=413,
            concept_name="Air pollution",
            concept_id="C559116025",
        ),
        NodeSpec(
            id="earth_geology",
            name="Geology",
            parent_id="earth_geoscience",
            order=421,
            concept_name="Geology",
        ),
        NodeSpec(
            id="earth_seismology",
            name="Seismology",
            parent_id="earth_geoscience",
            order=422,
            concept_name="Seismology",
        ),
        NodeSpec(
            id="earth_ocean",
            name="Oceanography",
            parent_id="earth_hydrosphere",
            order=431,
            concept_name="Oceanography",
        ),
        NodeSpec(
            id="earth_hydrology",
            name="Hydrological Modelling",
            parent_id="earth_hydrosphere",
            order=432,
            concept_name="Hydrological modelling",
        ),
        NodeSpec(
            id="earth_remote_sensing",
            name="Remote Sensing",
            parent_id="earth_observation",
            order=451,
            concept_name="Remote sensing",
        ),
        NodeSpec(
            id="earth_biodiversity",
            name="Biodiversity",
            parent_id="earth_ecosystems",
            order=441,
            concept_name="Biodiversity",
        ),
        NodeSpec(
            id="earth_biogeochemistry",
            name="Biogeochemistry",
            parent_id="earth_ecosystems",
            order=442,
            concept_name="Biogeochemistry",
            concept_id="C130309983",
        ),
        NodeSpec(
            id="earth_soil_science",
            name="Soil Science",
            parent_id="earth_ecosystems",
            order=443,
            concept_name="Soil science",
            concept_id="C159390177",
        ),
    ]

    earth_moves = {
        "climate": "earth_climate",
        "geophysics": "earth_geoscience",
        "ecology": "earth_ecosystems",
    }

    # --- Society ---
    society_new = [
        NodeSpec(
            id="soc_network_science",
            name="Network Science",
            parent_id="society",
            order=55,
            concept_name="Network science",
        ),
        NodeSpec(
            id="soc_sna",
            name="Social Network Analysis",
            parent_id="society",
            order=56,
            concept_name="Social network analysis",
        ),
        NodeSpec(
            id="soc_comp_socio",
            name="Computational Sociology",
            parent_id="society",
            order=57,
            concept_name="Computational sociology",
        ),
        NodeSpec(
            id="soc_social_media",
            name="Social Media",
            parent_id="society",
            order=58,
            concept_name="Social media",
        ),
        NodeSpec(
            id="soc_linguistics",
            name="Linguistics",
            parent_id="society",
            order=59,
            concept_name="Linguistics",
            concept_id="C41895202",
        ),
        NodeSpec(
            id="soc_public_policy",
            name="Public Policy",
            parent_id="society",
            order=60,
            concept_name="Public policy",
            concept_id="C109986646",
        ),
        NodeSpec(
            id="soc_law",
            name="Law",
            parent_id="society",
            order=61,
            concept_name="Law",
            concept_id="C199539241",
        ),
    ]

    # --- Engineering ---
    engineering_new = [
        NodeSpec(
            id="engineering",
            name="Engineering & Technology",
            parent_id="ai4sci",
            order=45,
            description="Engineering systems: control, chemical, electrical, mechanical, civil, aerospace, biomedical.",
        ),
        NodeSpec(
            id="eng_control",
            name="Control Engineering",
            parent_id="engineering",
            order=451,
            concept_name="Control engineering",
            concept_id="C133731056",
        ),
        NodeSpec(
            id="eng_chemical",
            name="Chemical Engineering",
            parent_id="engineering",
            order=452,
            concept_name="Chemical engineering",
            concept_id="C42360764",
        ),
        NodeSpec(
            id="eng_electrical",
            name="Electrical Engineering",
            parent_id="engineering",
            order=453,
            concept_name="Electrical engineering",
            concept_id="C119599485",
        ),
        NodeSpec(
            id="eng_mechanical",
            name="Mechanical Engineering",
            parent_id="engineering",
            order=454,
            concept_name="Mechanical engineering",
            concept_id="C78519656",
        ),
        NodeSpec(
            id="eng_civil",
            name="Civil Engineering",
            parent_id="engineering",
            order=455,
            concept_name="Civil engineering",
            concept_id="C147176958",
        ),
        NodeSpec(
            id="eng_aerospace",
            name="Aerospace Engineering",
            parent_id="engineering",
            order=456,
            concept_name="Aerospace engineering",
            concept_id="C146978453",
        ),
        NodeSpec(
            id="eng_biomedical",
            name="Biomedical Engineering",
            parent_id="engineering",
            order=457,
            concept_name="Biomedical engineering",
            concept_id="C136229726",
        ),
        NodeSpec(
            id="eng_systems",
            name="Systems Engineering",
            parent_id="engineering",
            order=458,
            concept_name="Systems engineering",
            concept_id="C201995342",
        ),
    ]

    # --- Formal sciences ---
    formal_new = [
        NodeSpec(
            id="formal",
            name="Formal Sciences",
            parent_id="ai4sci",
            order=55,
            description="Mathematics, statistics, optimization, and formal reasoning.",
        ),
        NodeSpec(
            id="formal_math",
            name="Mathematics",
            parent_id="formal",
            order=551,
            concept_name="Mathematics",
            concept_id="C33923547",
        ),
        NodeSpec(
            id="formal_stats",
            name="Statistics",
            parent_id="formal",
            order=552,
            concept_name="Statistics",
            concept_id="C105795698",
        ),
        NodeSpec(
            id="formal_optimization",
            name="Optimization",
            parent_id="formal",
            order=553,
            concept_name="Mathematical optimization",
            concept_id="C126255220",
        ),
        NodeSpec(
            id="formal_logic",
            name="Mathematical Logic",
            parent_id="formal",
            order=554,
            concept_name="Mathematical logic",
            concept_id="C47884741",
        ),
        NodeSpec(
            id="formal_atp",
            name="Automated Theorem Proving",
            parent_id="formal",
            order=555,
            concept_name="Automated theorem proving",
            concept_id="C206880738",
        ),
    ]

    # Apply new nodes.
    all_new = physics_new + chem_new + life_new + earth_new + society_new + engineering_new + formal_new
    for spec in all_new:
        nodes[spec.id] = node_obj(spec, existing=nodes.get(spec.id))

    # Apply moves.
    for nid, pid in {**physics_moves, **chem_moves, **life_moves, **earth_moves}.items():
        if nid in nodes:
            nodes[nid]["parentId"] = pid

    base["nodes"] = nodes
    BASE_JSON.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"[done] updated taxonomy: {BASE_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
