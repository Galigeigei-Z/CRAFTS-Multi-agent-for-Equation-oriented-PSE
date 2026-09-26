"""Fifty compact chemical-process variants used to expand the Web registry to 450 cases."""

from __future__ import annotations

from experiment.scripts.chemical_meaningful_batch_a_v4 import variant


def _units_and_arcs(recipe: str) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str, str]]]:
    templates = {
        "reaction_separation": (
            [
                ("FEED", "Feed", "reactant feed"),
                ("M101", "Mixer", "combine fresh and recovered reactants"),
                ("R101", "EquilibriumReactor", "chemically reactive conversion"),
                ("E101", "Cooler", "condition reactor effluent"),
                ("V101", "Flash", "recover product and unconverted reactants"),
                ("PRODUCT", "Product", "purified chemical product"),
                ("PURGE", "Product", "byproduct and inert purge"),
            ],
            [
                ("s01", "FEED.outlet", "M101.fresh", "fresh reactants"),
                ("s02", "M101.outlet", "R101.inlet", "reactor feed"),
                ("s03", "R101.outlet", "E101.inlet", "hot reactor effluent"),
                ("s04", "E101.outlet", "V101.inlet", "conditioned two-phase effluent"),
                ("s05", "V101.product", "PRODUCT.inlet", "recovered product"),
                ("s06", "V101.recycle", "M101.recycle", "unconverted reactant recycle"),
                ("s07", "V101.purge", "PURGE.inlet", "byproduct purge"),
            ],
        ),
        "absorption_regeneration": (
            [
                ("FEED", "Feed", "contaminated gas or liquid feed"),
                ("ABS101", "Absorber", "selective contaminant absorption"),
                ("HX101", "HeatExchanger", "rich-lean heat recovery"),
                ("REG101", "Stripper", "regenerate absorbent"),
                ("S101", "Separator", "absorbent recycle and purge"),
                ("CLEAN", "Product", "treated product"),
                ("RECOVERED", "Product", "recovered contaminant product"),
                ("PURGE", "Product", "degraded absorbent purge"),
            ],
            [
                ("s01", "FEED.outlet", "ABS101.feed", "contaminated feed"),
                ("s02", "ABS101.clean", "CLEAN.inlet", "treated product"),
                ("s03", "ABS101.rich", "HX101.rich_inlet", "rich absorbent"),
                ("s04", "HX101.rich_outlet", "REG101.inlet", "preheated rich absorbent"),
                ("s05", "REG101.lean", "HX101.lean_inlet", "hot lean absorbent"),
                ("s06", "HX101.lean_outlet", "S101.inlet", "cooled lean absorbent"),
                ("s07", "S101.recycle", "ABS101.solvent", "absorbent recycle"),
                ("s08", "S101.purge", "PURGE.inlet", "absorbent purge"),
                ("s09", "REG101.overhead", "RECOVERED.inlet", "recovered contaminant"),
            ],
        ),
        "crystallization_recycle": (
            [
                ("FEED", "Feed", "supersaturated or reactive liquor"),
                ("M101", "Mixer", "combine feed and seed recycle"),
                ("CR101", "Crystallizer", "controlled nucleation and crystal growth"),
                ("CF101", "SolidLiquidSeparator", "separate crystals and mother liquor"),
                ("S101", "Separator", "mother-liquor recycle and purge"),
                ("CRYSTAL", "Product", "washed crystal product"),
                ("PURGE", "Product", "impurity-controlled liquor purge"),
            ],
            [
                ("s01", "FEED.outlet", "M101.fresh", "fresh liquor"),
                ("s02", "M101.outlet", "CR101.inlet", "seeded crystallizer feed"),
                ("s03", "CR101.slurry", "CF101.inlet", "crystal slurry"),
                ("s04", "CF101.solids", "CRYSTAL.inlet", "crystal product"),
                ("s05", "CF101.liquid", "S101.inlet", "mother liquor"),
                ("s06", "S101.recycle", "M101.recycle", "seed and mother-liquor recycle"),
                ("s07", "S101.purge", "PURGE.inlet", "impurity purge"),
            ],
        ),
        "membrane_cascade": (
            [
                ("FEED", "Feed", "multicomponent membrane feed"),
                ("P101", "Pump", "first-stage pressure lift"),
                ("M101", "Membrane1D", "first membrane separation"),
                ("M201", "Nanofiltration", "selective polishing stage"),
                ("S101", "Separator", "retentate recycle and purge"),
                ("PRODUCT", "Product", "purified permeate product"),
                ("BRINE", "Product", "controlled concentrate purge"),
            ],
            [
                ("s01", "FEED.outlet", "P101.inlet", "membrane feed"),
                ("s02", "P101.outlet", "M101.inlet", "pressurized feed"),
                ("s03", "M101.permeate", "M201.inlet", "first-stage permeate"),
                ("s04", "M201.permeate", "PRODUCT.inlet", "polished product"),
                ("s05", "M101.retentate", "S101.inlet", "first-stage concentrate"),
                ("s06", "S101.recycle", "P101.recycle", "concentrate recycle"),
                ("s07", "S101.purge", "BRINE.inlet", "concentrate purge"),
            ],
        ),
        "adsorption_regeneration": (
            [
                ("FEED", "Feed", "contaminated process feed"),
                ("A101", "Adsorber", "lead adsorption bed"),
                ("A102", "Adsorber", "lag polishing bed"),
                ("RG101", "ThermalRegenerator", "regenerate loaded sorbent"),
                ("S101", "Separator", "regenerated sorbent return and purge"),
                ("PRODUCT", "Product", "treated product"),
                ("WASTE", "Product", "concentrated contaminant purge"),
            ],
            [
                ("s01", "FEED.outlet", "A101.inlet", "contaminated feed"),
                ("s02", "A101.outlet", "A102.inlet", "lead-bed effluent"),
                ("s03", "A102.outlet", "PRODUCT.inlet", "polished product"),
                ("s04", "A101.loaded", "RG101.inlet", "loaded sorbent"),
                ("s05", "RG101.regenerated", "S101.inlet", "regenerated sorbent"),
                ("s06", "S101.recycle", "A102.sorbent", "sorbent recycle"),
                ("s07", "S101.purge", "WASTE.inlet", "contaminant purge"),
            ],
        ),
        "wastewater_resource_recovery": (
            [
                ("FEED", "Feed", "wastewater feed"),
                ("R101", "AnoxicReactor", "anoxic biological conversion"),
                ("R201", "AerationTank", "aerobic polishing and nutrient uptake"),
                ("CL101", "Clarifier", "biomass and liquid separation"),
                ("S101", "Separator", "return sludge and waste split"),
                ("EFFLUENT", "Product", "treated effluent"),
                ("RESOURCE", "Product", "recovered nutrient or biosolids"),
            ],
            [
                ("s01", "FEED.outlet", "R101.inlet", "wastewater feed"),
                ("s02", "R101.outlet", "R201.inlet", "anoxic effluent"),
                ("s03", "R201.outlet", "CL101.inlet", "mixed liquor"),
                ("s04", "CL101.overflow", "EFFLUENT.inlet", "treated effluent"),
                ("s05", "CL101.sludge", "S101.inlet", "settled biomass"),
                ("s06", "S101.recycle", "R101.recycle", "return biomass recycle"),
                ("s07", "S101.product", "RESOURCE.inlet", "resource product"),
            ],
        ),
        "distillation_heat_integration": (
            [
                ("FEED", "Feed", "multicomponent distillation feed"),
                ("T101", "DistillationColumn", "fractionation column"),
                ("E101", "Condenser", "overhead condensation"),
                ("E102", "Reboiler", "bottoms vaporization"),
                ("S101", "Separator", "reflux and distillate split"),
                ("DISTILLATE", "Product", "light product"),
                ("BOTTOMS", "Product", "heavy product"),
            ],
            [
                ("s01", "FEED.outlet", "T101.feed", "column feed"),
                ("s02", "T101.overhead", "E101.inlet", "overhead vapor"),
                ("s03", "E101.liquid", "S101.inlet", "condensed overhead"),
                ("s04", "S101.reflux", "T101.reflux", "column reflux"),
                ("s05", "S101.product", "DISTILLATE.inlet", "distillate product"),
                ("s06", "T101.bottoms", "E102.inlet", "bottom liquid"),
                ("s07", "E102.vapor", "T101.boilup", "reboiler vapor return"),
                ("s08", "E102.product", "BOTTOMS.inlet", "bottoms product"),
            ],
        ),
        "gas_cleanup_recovery": (
            [
                ("FEED", "Feed", "raw process gas"),
                ("C101", "Compressor", "gas compression"),
                ("E101", "Cooler", "aftercooling and liquid dropout"),
                ("G101", "GuardBed", "reactive trace-contaminant removal"),
                ("M101", "Membrane1D", "bulk gas separation"),
                ("PRODUCT", "Product", "pipeline-quality gas"),
                ("RECOVERED", "Product", "recovered carbon or sulfur stream"),
            ],
            [
                ("s01", "FEED.outlet", "C101.inlet", "raw gas"),
                ("s02", "C101.outlet", "E101.inlet", "compressed hot gas"),
                ("s03", "E101.outlet", "G101.inlet", "cooled gas"),
                ("s04", "G101.outlet", "M101.inlet", "guarded gas"),
                ("s05", "M101.retentate", "PRODUCT.inlet", "clean product gas"),
                ("s06", "M101.permeate", "RECOVERED.inlet", "recovered contaminant stream"),
            ],
        ),
        "solvent_extraction_recycle": (
            [
                ("FEED", "Feed", "metal-bearing aqueous feed"),
                ("EX101", "MixerSettler", "metal extraction"),
                ("SC101", "MixerSettler", "loaded-organic scrub"),
                ("ST101", "MixerSettler", "metal stripping"),
                ("S101", "Separator", "organic recycle and purge"),
                ("PRODUCT", "Product", "concentrated metal product"),
                ("RAFFINATE", "Product", "depleted aqueous raffinate"),
            ],
            [
                ("s01", "FEED.outlet", "EX101.aqueous", "metal-bearing feed"),
                ("s02", "EX101.organic", "SC101.inlet", "loaded organic"),
                ("s03", "SC101.outlet", "ST101.inlet", "scrubbed organic"),
                ("s04", "ST101.product", "PRODUCT.inlet", "stripped metal product"),
                ("s05", "ST101.organic", "S101.inlet", "lean organic"),
                ("s06", "S101.recycle", "EX101.recycle", "organic recycle"),
                ("s07", "EX101.raffinate", "RAFFINATE.inlet", "aqueous raffinate"),
            ],
        ),
        "electrochemical_recycle": (
            [
                ("FEED", "Feed", "ionic process feed"),
                ("M101", "Mixer", "feed conditioning and recycle mixing"),
                ("EC101", "Electrodialysis1D", "selective ionic transport"),
                ("S101", "Separator", "concentrate recycle and product split"),
                ("PRODUCT", "Product", "recovered ionic product"),
                ("DILUATE", "Product", "depleted treated stream"),
                ("PURGE", "Product", "impurity-controlled purge"),
            ],
            [
                ("s01", "FEED.outlet", "M101.fresh", "ionic feed"),
                ("s02", "M101.outlet", "EC101.inlet", "conditioned stack feed"),
                ("s03", "EC101.concentrate", "S101.inlet", "concentrated product loop"),
                ("s04", "S101.recycle", "M101.recycle", "concentrate recycle"),
                ("s05", "S101.product", "PRODUCT.inlet", "recovered ionic product"),
                ("s06", "EC101.diluate", "DILUATE.inlet", "treated diluate"),
                ("s07", "S101.purge", "PURGE.inlet", "impurity purge"),
            ],
        ),
    }
    return templates[recipe]


def compact_variant(
    key: str,
    label: str,
    parent: str,
    process_family: str,
    recipe: str,
    prompt: str,
    distinction: str,
    components: tuple[str, ...],
    tags: tuple[str, ...],
    profile: int,
) -> dict:
    units, arcs = _units_and_arcs(recipe)
    row = variant(
        key,
        label,
        parent,
        process_family,
        key.removeprefix("variant_"),
        prompt,
        distinction,
        units,
        arcs,
        (*tags, "compact_flowsheet", recipe),
    )
    row.update({"recipe": recipe, "components": list(components), "profile": profile})
    return row


def v(*args, **kwargs) -> dict:
    return compact_variant(*args, **kwargs)


BATCH = (
    # Reaction and phase-separation tasks.
    v("variant_idaes_ammonia_synthesis_intercool_condense", "Ammonia Synthesis with Intercooling and NH3 Condensation", "blind_synthesized_methanol_single", "reaction_separation", "reaction_separation", "Build a compact ammonia loop with synthesis, effluent cooling, ammonia condensation, reactant recycle and inert purge.", "Introduces nitrogen-hydrogen reaction, ammonia phase recovery and an inert-limited recycle purge.", ("N2", "H2", "NH3", "Ar"), ("ammonia", "reaction", "recycle"), 0),
    v("variant_idaes_ethanol_dehydration_water_knockout", "Ethanol Dehydration with Water Knockout and Ethylene Recovery", "blind_synthesized_hda_flash", "reaction_separation", "reaction_separation", "Build an ethanol-dehydration reactor followed by cooling, water knockout, ethylene recovery and ethanol recycle.", "Couples equilibrium conversion to water condensation and unreacted-ethanol recycle.", ("ethanol", "ethylene", "H2O", "ether"), ("dehydration", "ethylene", "phase_separation"), 1),
    v("variant_idaes_wgs_shift_condensate_recycle", "Water-Gas Shift with Condensate Knockout and Steam Recycle", "reaktoro_biogas_combustion", "reaction_separation", "reaction_separation", "Build a compact water-gas-shift train with effluent cooling, condensate knockout and steam recycle while maximizing hydrogen recovery.", "Adds reactive CO conversion and condensate recycle under a minimum steam-to-carbon constraint.", ("CO", "H2O", "CO2", "H2"), ("hydrogen", "water_gas_shift", "steam_recycle"), 2),
    v("variant_idaes_methanation_co2_recycle", "CO2 Methanation with Water Knockout and Gas Recycle", "variant_idaes_sour_gas_dehydration_sulfur_co2_capture", "reaction_separation", "reaction_separation", "Build a Sabatier methanation loop with product-water condensation, methane recovery and unconverted-gas recycle.", "Adds CO2 hydrogenation stoichiometry and water removal before recycle.", ("CO2", "H2", "CH4", "H2O"), ("methanation", "carbon_utilization", "gas_recycle"), 3),
    v("variant_idaes_formaldehyde_reactor_absorber", "Methanol Oxidation with Formaldehyde Recovery", "blind_synthesized_methanol_recycle", "reaction_separation", "reaction_separation", "Build a compact methanol-oxidation process with reactor cooling, formaldehyde recovery and methanol recycle.", "Changes methanol service from synthesis to selective oxidation with oxygen-limited conversion and condensable product recovery.", ("CH3OH", "O2", "CH2O", "H2O"), ("formaldehyde", "oxidation", "methanol_recycle"), 4),

    # Absorption and solvent-regeneration tasks.
    v("variant_idaes_mea_absorber_flash_regeneration", "MEA CO2 Capture with Rich Flash and Solvent Regeneration", "official_idaes_pz_afs_carbon_capture", "carbon_capture", "absorption_regeneration", "Build a compact MEA absorber-regenerator loop with rich-solvent heat recovery, CO2 product and degradation purge.", "Uses aqueous MEA chemistry and a rich/lean loop distinct from the registered piperazine AFS topology.", ("CO2", "MEA", "H2O", "heat_stable_salts"), ("absorption", "co2_capture", "solvent_recycle"), 0),
    v("variant_reflo_voc_air_stripper_condensate_recovery", "VOC Air Stripping with Condensate Recovery", "reflo_air_stripping_0d", "air_stripping", "absorption_regeneration", "Couple air stripping to selective offgas absorption, solvent regeneration and VOC product recovery.", "Closes the VOC path with regenerable absorption instead of atmospheric transfer.", ("H2O", "VOC", "air", "absorbent"), ("air_stripping", "voc_recovery", "offgas_treatment"), 1),
    v("variant_watertap_biogas_co2_water_scrubber", "Biogas CO2 Water Scrubbing with Methane Recovery", "variant_watertap_adm1_biogas_water_scrubbing", "resource_recovery", "absorption_regeneration", "Build a water-scrubbing loop for biogas upgrading with methane product, CO2 recovery and regenerated wash water.", "Separates methane and carbon dioxide while recycling regenerated physical solvent.", ("CH4", "CO2", "H2S", "H2O"), ("biogas", "co2_recovery", "water_scrubbing"), 2),
    v("variant_idaes_teg_dehydration_flash_regeneration", "TEG Dehydration with Flash-Gas Recovery", "variant_idaes_natural_gas_glycol_dehydration", "gas_processing", "absorption_regeneration", "Build a compact TEG dehydration loop with rich-glycol heat recovery, regeneration, flash-gas recovery and glycol purge.", "Adds dissolved-hydrocarbon flash recovery and degraded-glycol purge to the dehydration loop.", ("CH4", "H2O", "TEG", "BTEX"), ("dehydration", "natural_gas", "teg_regeneration"), 3),
    v("variant_watertap_ammonia_acid_absorption_crystallization", "Ammonia Acid Absorption with Ammonium-Salt Recovery", "variant_watertap_ammonia_membrane_contactor_heat_recovery", "resource_recovery", "absorption_regeneration", "Capture ammonia in an acid absorbent, regenerate the circulating liquor and recover concentrated ammonium salt.", "Adds acid-base capture chemistry, absorbent recycle and a bounded salt-product purge.", ("NH3", "H2SO4", "NH4+", "SO4--"), ("ammonia_recovery", "acid_absorption", "fertilizer"), 4),

    # Crystallization and precipitation tasks.
    v("variant_reflo_nacl_seeded_cooling_crystallization", "Seeded NaCl Cooling Crystallization", "reflo_crystallizer_effect", "crystallization", "crystallization_recycle", "Build seeded NaCl crystallization with crystal separation, mother-liquor recycle and impurity purge.", "Adds seed recycle and impurity control to a single crystallizer effect.", ("H2O", "NaCl", "CaSO4"), ("nacl", "seed_recycle", "crystallization"), 0),
    v("variant_watertap_gypsum_precipitation_seed_recycle", "Gypsum Precipitation with Seed Recycle", "variant_watertap_two_stage_crystallization", "crystallization", "crystallization_recycle", "Precipitate gypsum from calcium-sulfate brine with seed recycle and a chloride-controlled purge.", "Changes the solid product and precipitation chemistry from NaCl to CaSO4 dihydrate.", ("Ca++", "SO4--", "CaSO4_2H2O", "Cl-"), ("gypsum", "precipitation", "seed_recycle"), 1),
    v("variant_watertap_struvite_ph_control_crystallization", "Struvite Crystallization with pH Control", "variant_watertap_mdc_osmotic_crystallization", "resource_recovery", "crystallization_recycle", "Recover struvite from ammonium-phosphate liquor using magnesium dosing, seeded crystallization and mother-liquor recycle.", "Adds Mg-N-P reaction stoichiometry and a pH-dependent struvite product constraint.", ("Mg++", "NH4+", "PO4---", "MgNH4PO4_6H2O"), ("struvite", "ph_control", "nutrient_recovery"), 2),
    v("variant_prommis_lithium_carbonate_seed_recycle", "Lithium Carbonate Precipitation with Seed Recycle", "variant_prommis_lithium_nf_bped_crystallization", "critical_materials", "crystallization_recycle", "Precipitate battery-grade lithium carbonate with carbonate dosing, seed recycle and sodium impurity purge.", "Makes lithium recovery and sodium rejection explicit in a compact precipitation circuit.", ("Li+", "CO3--", "Li2CO3", "Na+"), ("lithium", "carbonate", "critical_materials"), 3),
    v("variant_prommis_ree_oxalate_precipitation_wash", "REE Oxalate Precipitation with Crystal Washing", "reaktoro_thermal_precipitation", "critical_materials", "crystallization_recycle", "Recover rare-earth oxalate crystals with precipitation, mother-liquor recycle, crystal washing and impurity purge.", "Introduces oxalate complexation and washed REE solid recovery rather than generic thermal precipitation.", ("REE+++", "oxalate", "REE_oxalate", "Fe+++"), ("rare_earth", "oxalate", "crystal_washing"), 4),

    # Membrane cascades.
    v("variant_watertap_ro_nf_softening_pretreatment", "NF-RO Softening and Desalination Cascade", "watertap_seawater_ro_desalination", "membrane_separation", "membrane_cascade", "Build a compact NF-RO cascade that removes hardness before desalination and recycles a bounded concentrate fraction.", "Adds divalent-ion-selective pretreatment ahead of salt-rejecting RO.", ("H2O", "Na+", "Cl-", "Ca++", "Mg++"), ("nanofiltration", "reverse_osmosis", "softening"), 0),
    v("variant_idaes_co2_h2_membrane_two_stage", "Two-Stage CO2-H2 Membrane Separation", "idaes_co2_membrane_1d", "membrane_separation", "membrane_cascade", "Build two membrane stages with hydrogen product polishing and CO2-rich retentate recycle.", "Changes the membrane service to hydrogen purification with explicit stage coupling.", ("H2", "CO2", "CO", "CH4"), ("hydrogen", "co2_membrane", "two_stage"), 1),
    v("variant_prommis_li_mg_nf_diafiltration", "Lithium-Magnesium NF with Diafiltration", "blind_synthesized_prommis_nanofiltration_membrane_schematic", "membrane_separation", "membrane_cascade", "Build a nanofiltration-diafiltration cascade for lithium recovery with magnesium-rich retentate recycle.", "Adds wash-water diafiltration and Li/Mg selectivity to the membrane cascade.", ("Li+", "Mg++", "Na+", "Cl-", "H2O"), ("lithium", "magnesium", "diafiltration"), 2),
    v("variant_idaes_ethanol_water_pervaporation_polish", "Ethanol-Water Pervaporation Polishing Cascade", "official_idaes_skeleton_pervaporation", "pervaporation_membrane_separation", "membrane_cascade", "Build a two-stage pervaporation polishing train with retentate recycle and concentrated water permeate removal.", "Extends the official skeleton pervaporation case with a second selective polishing stage.", ("ethanol", "H2O", "water_vapor"), ("pervaporation", "ethanol", "dehydration"), 3),
    v("variant_watertap_oaro_ro_hybrid", "OARO-RO Hybrid with Draw Recycle", "watertap_oaro_multi", "membrane_separation", "membrane_cascade", "Build a compact OARO-RO hybrid with draw recycle and a final product-polishing membrane.", "Adds an RO polishing stage and concentrate recycle around an OARO core.", ("H2O", "NaCl", "draw_solution"), ("oaro", "reverse_osmosis", "draw_recycle"), 4),

    # Adsorption and ion-exchange tasks.
    v("variant_watertap_gac_pfas_lead_lag", "Lead-Lag GAC for PFAS with Regeneration", "blind_synthesized_gac_unit", "adsorption", "adsorption_regeneration", "Build lead-lag GAC adsorption for PFAS with thermal regeneration, carbon recycle and concentrated waste isolation.", "Changes the adsorbate to persistent PFAS and requires a high-destruction regeneration purge.", ("H2O", "PFAS", "activated_carbon"), ("pfas", "gac", "lead_lag"), 0),
    v("variant_idaes_tsa_water_co2_coadsorption", "Dual-Bed TSA for Water and CO2 Coadsorption", "idaes_temperature_swing_adsorption", "adsorption", "adsorption_regeneration", "Build dual-bed TSA that removes both water and carbon dioxide with heat-integrated regeneration.", "Introduces competitive H2O/CO2 loading and regenerated-bed recycle.", ("CH4", "CO2", "H2O", "zeolite"), ("tsa", "coadsorption", "gas_drying"), 1),
    v("variant_idaes_vsa_co2_dual_bed", "Dual-Bed Vacuum-Swing CO2 Capture", "official_co2_adsorption_desorption", "carbon_capture", "adsorption_regeneration", "Build a dual-bed vacuum-swing adsorption cycle with CO2 product recovery and pressure equalization.", "Changes regeneration from the registered steam/desorption path to vacuum swing with bed equalization.", ("N2", "CO2", "adsorbent"), ("vsa", "co2_capture", "dual_bed"), 2),
    v("variant_idaes_zno_h2s_guard_regeneration", "ZnO H2S Guard Bed with Sorbent Regeneration", "variant_natural_gas_zno_guard_claus_sulfur_recovery", "gas_processing", "adsorption_regeneration", "Build lead-lag ZnO sulfur guard beds with controlled regeneration and sulfur-rich purge recovery.", "Uses reactive sulfur capture and bounded ZnO capacity restoration.", ("CH4", "H2S", "ZnO", "ZnS"), ("h2s", "zno", "guard_bed"), 3),
    v("variant_watertap_ix_ammonium_regeneration", "Ammonium Ion Exchange with Regenerant Recycle", "watertap_ion_exchange", "ion_exchange", "adsorption_regeneration", "Build ammonium-selective ion exchange with brine regeneration, regenerant recycle and ammonia recovery.", "Changes IX selectivity from hardness removal to ammonium recovery and closes the regenerant loop.", ("H2O", "NH4+", "Na+", "Cl-", "resin"), ("ammonium", "ion_exchange", "regeneration"), 4),

    # Wastewater and resource-recovery tasks.
    v("variant_watertap_anoxic_aerobic_nitrate_recycle", "Anoxic-Aerobic BNR with Nitrate Recycle", "watertap_asm1", "wastewater_treatment", "wastewater_resource_recovery", "Build a compact anoxic-aerobic activated-sludge train with internal nitrate recycle and sludge wasting.", "Adds an explicit nitrate recycle linking anoxic carbon use to aerobic nitrification.", ("COD", "NH4+", "NO3-", "biomass"), ("bnr", "nitrate_recycle", "asm1"), 0),
    v("variant_watertap_ebpr_struvite_sidestream", "EBPR with Sidestream Struvite Recovery", "watertap_asm2d", "wastewater_resource_recovery", "wastewater_resource_recovery", "Build compact biological phosphorus removal with sludge separation and sidestream struvite recovery.", "Couples ASM2d phosphorus uptake to a recoverable mineral product.", ("COD", "NH4+", "PO4---", "biomass", "struvite"), ("ebpr", "struvite", "asm2d"), 1),
    v("variant_watertap_ad_digestate_dewatering_recycle", "Anaerobic Digestion with Digestate Dewatering Recycle", "watertap_anaerobic_digester_unit", "wastewater_resource_recovery", "wastewater_resource_recovery", "Build anaerobic digestion followed by solids separation, centrate recycle and biosolids recovery.", "Adds digestate phase separation and a nitrogen-limited centrate recycle.", ("COD", "CH4", "NH4+", "biosolids"), ("anaerobic_digestion", "dewatering", "centrate_recycle"), 2),
    v("variant_watertap_electronp_nutrient_polishing", "ElectroNP Nutrient Polishing with Solids Recycle", "blind_synthesized_watertap_electroNP_flowsheet", "wastewater_resource_recovery", "wastewater_resource_recovery", "Build a compact biological train with ElectroNP polishing, clarifier recycle and nutrient-product recovery.", "Adds electrochemical nitrogen/phosphorus recovery after biological conversion.", ("COD", "NH4+", "PO4---", "N_product", "P_product"), ("electronp", "nutrient_recovery", "polishing"), 3),
    v("variant_watertap_wrrf_equalization_bnr", "Equalization-BNR Train for Peak Wet-Weather Flow", "watertap_uconn_wrrf", "wastewater_treatment", "wastewater_resource_recovery", "Build a compact equalized biological nutrient-removal train with return sludge and wet-weather solids recovery.", "Introduces peak-flow equalization and recycle control ahead of nutrient removal.", ("H2O", "COD", "NH4+", "NO3-", "biomass"), ("equalization", "bnr", "wet_weather"), 4),

    # Distillation and heat-integration tasks.
    v("variant_idaes_hda_benzene_toluene_side_draw", "HDA Benzene-Toluene Column with Side Draw", "blind_synthesized_hda_distillation", "distillation", "distillation_heat_integration", "Build a compact HDA product column with benzene distillate, toluene recycle bottoms and a heavy-aromatic side draw.", "Adds a chemically distinct side draw that controls heavy-aromatic buildup.", ("benzene", "toluene", "diphenyl", "H2"), ("hda", "side_draw", "benzene"), 0),
    v("variant_idaes_methanol_water_pressure_swing", "Methanol-Water Pressure-Swing Distillation", "variant_methanol_water_nrtl_partial_condensation", "distillation", "distillation_heat_integration", "Build a compact pressure-swing methanol-water column with heat recovery and methanol recycle.", "Changes VLE pressure and closes methanol recovery around a nonideal binary split.", ("methanol", "H2O"), ("pressure_swing", "methanol", "nonideal_vle"), 1),
    v("variant_idaes_btx_extractive_solvent_recycle", "BTX Extractive Distillation with Solvent Recycle", "variant_idaes_btx_extractive_distillation_solvent_recycle", "distillation", "distillation_heat_integration", "Build a compact extractive-distillation column with aromatic product, solvent recovery and lean-solvent recycle.", "Retains explicit solvent-enhanced relative volatility while reducing the topology to one column and recycle loop.", ("benzene", "toluene", "xylene", "sulfolane"), ("btx", "extractive_distillation", "solvent_recycle"), 2),
    v("variant_idaes_teg_regenerator_stripping_column", "TEG Regenerator with Water Stripping and Glycol Recycle", "variant_idaes_natural_gas_glycol_dehydration", "distillation", "distillation_heat_integration", "Build a compact TEG regeneration column with overhead water removal, reflux and lean-glycol recycle.", "Focuses on the glycol-water fractionation subflowsheet and heat recovery.", ("TEG", "H2O", "CH4", "BTEX"), ("teg", "regeneration", "stripping"), 3),
    v("variant_idaes_propane_propylene_heat_pump", "Propane-Propylene Splitter with Vapor Recompression", "variant_hda_distillation_heat_pump", "distillation", "distillation_heat_integration", "Build a compact propane-propylene splitter with vapor-recompression heat integration and polymer-grade propylene product.", "Changes the close-boiling service and uses overhead compression to reduce reboiler duty.", ("propane", "propylene"), ("c3_splitter", "heat_pump", "vapor_recompression"), 4),

    # Gas cleanup and recovery tasks.
    v("variant_idaes_pipeline_teg_compressor_aftercool", "Pipeline Compression with TEG Drying and Aftercooling", "idaes_natural_gas_pipeline_network", "gas_processing", "gas_cleanup_recovery", "Build a compact natural-gas compression, aftercooling, sulfur guard and dehydration train.", "Adds water and sulfur cleanup around a pipeline compressor station.", ("CH4", "CO2", "H2O", "H2S"), ("pipeline", "compression", "dehydration"), 0),
    v("variant_idaes_sour_gas_zno_claus_tailgas", "Sour-Gas Guard and Sulfur-Recovery Pretreatment", "variant_natural_gas_zno_guard_claus_sulfur_recovery", "gas_processing", "gas_cleanup_recovery", "Build a compact sour-gas compression and ZnO guard train with sulfur-rich recovery feed.", "Separates bulk acid gas after reactive trace-H2S polishing.", ("CH4", "H2S", "CO2", "sulfur"), ("sour_gas", "zno", "sulfur_recovery"), 1),
    v("variant_idaes_hda_psa_tailgas_recycle", "HDA Offgas Compression with Hydrogen Recovery", "variant_hda_psa_hydrogen_recovery_tailgas_fuel", "gas_processing", "gas_cleanup_recovery", "Build compact HDA offgas conditioning with methane guard, hydrogen membrane recovery and tail-gas product.", "Reduces the PSA concept to a small pressure-driven H2 recovery subflowsheet.", ("H2", "CH4", "benzene", "toluene"), ("hda", "hydrogen_recovery", "offgas"), 2),
    v("variant_idaes_co2_membrane_recompress_recycle", "CO2 Membrane with Permeate Recompression", "variant_idaes_co2_membrane_two_stage_recycle", "gas_processing", "gas_cleanup_recovery", "Build a compact CO2 membrane train with permeate recompression and carbon-product recovery.", "Adds pressure recovery and a bounded permeate recycle to bulk CO2 separation.", ("CO2", "N2", "O2", "H2O"), ("co2_membrane", "recompression", "carbon_capture"), 3),
    v("variant_idaes_biogas_h2s_co2_polishing", "Biogas H2S Guard and CO2 Membrane Polishing", "variant_watertap_adm1_biogas_water_scrubbing", "gas_processing", "gas_cleanup_recovery", "Build compact biogas compression, H2S guard and CO2 membrane polishing to pipeline methane.", "Combines reactive sulfur removal with bulk CO2 membrane separation.", ("CH4", "CO2", "H2S", "H2O"), ("biogas", "h2s", "co2_polishing"), 4),

    # Solvent-extraction circuits.
    v("variant_prommis_ree_sx_scrub_strip", "REE Solvent Extraction with Scrub and Strip", "prommis_dynamic_mixer_settler", "hydrometallurgy", "solvent_extraction_recycle", "Build a compact REE extraction-scrub-strip circuit with organic recycle and impurity raffinate.", "Uses staged pH-dependent rare-earth transfer with explicit organic closure.", ("REE+++", "Fe+++", "extractant", "acid"), ("rare_earth", "solvent_extraction", "scrub_strip"), 0),
    v("variant_prommis_cobalt_nickel_sx_recycle", "Cobalt-Nickel Solvent Extraction with Organic Recycle", "blind_synthesized_prommis_solvent_extraction_steady", "hydrometallurgy", "solvent_extraction_recycle", "Separate cobalt from nickel in a compact extraction-scrub-strip circuit with organic recycle.", "Introduces Co/Ni selectivity and acid-controlled stripping.", ("Co++", "Ni++", "extractant", "H+"), ("cobalt", "nickel", "solvent_extraction"), 1),
    v("variant_prommis_copper_sxew_raffinate", "Copper SX with Raffinate Recycle", "variant_prommis_copper_leach_sxew_raffinate_recycle", "hydrometallurgy", "solvent_extraction_recycle", "Build a compact copper extraction and stripping circuit with lean-organic and raffinate recycle boundaries.", "Retains Cu/Fe selectivity while exposing the SX material loops separately from electrowinning.", ("Cu++", "Fe+++", "extractant", "H2SO4"), ("copper", "raffinate", "sxew"), 2),
    v("variant_prommis_lithium_sx_solvent_wash", "Lithium Solvent Extraction with Solvent Wash", "variant_prommis_sx_scrub_strip_organic_recycle", "critical_materials", "solvent_extraction_recycle", "Build lithium extraction, magnesium scrub, lithium strip and organic-solvent wash with recycle.", "Adds a solvent-wash step to control magnesium carryover into lithium product.", ("Li+", "Mg++", "extractant", "HCl"), ("lithium", "magnesium", "solvent_wash"), 3),
    v("variant_prommis_ree_leach_sx_acid_recycle_small", "Compact REE Leach-Liquor Solvent Extraction", "variant_prommis_ree_leach_sx_bped_acid_loop", "critical_materials", "solvent_extraction_recycle", "Build a compact REE extraction-scrub-strip loop with acid recovery and aqueous raffinate product.", "Reduces the integrated leach-BPED train to a focused SX acid-recycle task.", ("REE+++", "Fe+++", "oxalate", "H+", "extractant"), ("rare_earth", "acid_recycle", "critical_materials"), 4),

    # Electrochemical separations.
    v("variant_watertap_bped_ix_brine_recovery_small", "Compact BPED Recovery from Ion-Exchange Brine", "variant_watertap_bped_ix_brine_acid_base_recovery", "electrochemical_separation", "electrochemical_recycle", "Build compact BPED salt splitting with concentrate recycle, acid/base product recovery and impurity purge.", "Focuses on the electrochemical brine-recovery core with explicit recycle closure.", ("Na+", "Cl-", "H+", "OH-", "Ca++"), ("bped", "ix_brine", "acid_base"), 0),
    v("variant_watertap_ed_nitrate_concentrate_recycle", "Electrodialysis Nitrate Recovery with Concentrate Recycle", "blind_synthesized_electrodialysis_1stack", "electrochemical_separation", "electrochemical_recycle", "Recover nitrate by electrodialysis with concentrate recycle and a salinity-controlled purge.", "Changes the transported ion and closes a fertilizer-concentrate loop.", ("NO3-", "Na+", "Cl-", "H2O"), ("electrodialysis", "nitrate", "fertilizer"), 1),
    v("variant_watertap_electronp_struvite_polish", "ElectroNP Phosphate Recovery with Product Polishing", "blind_synthesized_watertap_electroNP_flowsheet", "electrochemical_separation", "electrochemical_recycle", "Build compact electrochemical phosphate recovery with recycle, product polishing and impurity purge.", "Adds a polishing split around the ElectroNP product loop.", ("PO4---", "NH4+", "Mg++", "struvite"), ("electronp", "phosphate", "product_polishing"), 2),
    v("variant_idaes_co2_electrolysis_gas_recycle_small", "CO2 Electrolysis with Gas Recycle", "variant_idaes_co2_electroreduction_gas_recycle", "electrochemical_reaction", "electrochemical_recycle", "Build compact CO2 electrolysis with cathode-gas recovery, unconverted CO2 recycle and carbonate purge.", "Focuses on carbon conversion and carbonate closure around one electrochemical stack.", ("CO2", "CO", "H2", "carbonate", "H2O"), ("co2_electrolysis", "gas_recycle", "carbonate"), 3),
    v("variant_watertap_edr_softening_purge", "EDR Softening with Polarity-Reversal Purge", "variant_watertap_bped_ix_brine_acid_base_recovery", "electrochemical_separation", "electrochemical_recycle", "Build electrodialysis-reversal softening with concentrate recycle and a hardness-controlled reversal purge.", "Introduces divalent-ion transport and periodic purge control rather than acid/base generation.", ("Ca++", "Mg++", "Na+", "Cl-", "H2O"), ("edr", "softening", "polarity_reversal"), 4),
)


BY_KEY = {row["key"]: row for row in BATCH}
COMPONENTS = {row["mode"]: row["components"] for row in BATCH}

if len(BATCH) != 50 or len(BY_KEY) != 50 or len(COMPONENTS) != 50:
    raise RuntimeError("batch K must contain 50 unique cases and modes")
