# CRAFTS: Multi-Agent Automation for Equation-Oriented Process Simulation

CRAFTS is a research framework for translating natural-language process
requirements and optional process-flow-diagram evidence into inspectable,
equation-oriented chemical-process models.

The framework mirrors the staged work of chemical engineers. Seven
model-backed agents collaborate through typed intermediate artifacts, while
deterministic engineering gates validate each handoff before model
construction, initialization, solving, and eligible optimization.

> **Repository status:** this public repository is being prepared as a
> conservative research demo. The initial release will document the
> architecture and artifact contracts without distributing benchmark source
> data, evaluation records, trained weights, or private execution
> infrastructure.

## Architecture

CRAFTS uses seven bounded agent roles:

1. **Input Understanding** preserves requirements, relations, constraints,
   exclusions, and ambiguities.
2. **Intent Router** organizes the request into process-level semantics using
   fixed chemical-engineering knowledge.
3. **Visual Descriptor** converts permitted raster PFD evidence into a typed
   `VisualGraphIR`.
4. **Topology Agent** proposes units, ports, directed streams,
   thermodynamic assignments, and recycle structure in `TopologyIR`.
5. **Specification Agent** proposes grounded operating targets, values, units,
   and fixed/free intent in `SpecIR`.
6. **Debug Agent** diagnoses a failed layer and proposes a bounded,
   stage-compatible repair directive.
7. **Optimization Agent** proposes an objective, decision variables, and
   constraints only after a valid solve and only when optimization is
   requested.

The roles are coordinated as a LangGraph workflow. Deterministic validators,
the degree-of-freedom checker, BuildPlan compiler, simulator, failure router,
repair executor, optimizer, audit sink, and evaluator are control/tool nodes;
they are not counted as additional agents.

```text
Natural-language request + optional PFD
  -> Input Understanding -> GroundedRequestIR -> contract gate
  -> Intent Router -> ChEEvidenceBundle -> contract gate
  -> role-scoped ChE visibility gateway
  -> [PFD available] Visual Descriptor -> VisualGraphIR -> contract gate
  -> Topology Agent -> TopologyIR -> topology and compatibility gates
  -> Specification Agent -> SpecIR -> target and DoF gates
  -> deterministic compiler -> BuildPlanIR -> contract gate
  -> materialize -> initialize -> solve -> SolveReport -> acceptance gate
  -> [optimization requested] Optimization Agent -> OptimizationPlanIR
     -> deterministic validation and optimization -> OptimizationReport
  -> RunAudit
```

A failed artifact returns only to its owning stage through the bounded Debug
path. Unsupported or exhausted trajectories terminate without substituting a
different artifact or execution path.

## Knowledge and visibility boundary

The modeling roles are guided by reusable chemical-engineering knowledge:
unit-operation semantics, material and energy-flow relations, thermodynamic
compatibility, legal ports, degree-of-freedom closure, initialization
requirements, and verified simulator capabilities.

Role-visible context is scoped and auditable. Raw raster evidence is available
only to the Visual Descriptor. Downstream roles receive accepted typed
artifacts, and evaluator-only references and scoring records remain outside
model-visible context.

## Fine-tuning

Role-specific fine-tuning is applied to the three schema-critical
transformations:

- Visual Descriptor: PFD evidence to `VisualGraphIR`
- Topology Agent: process evidence to `TopologyIR`
- Specification Agent: accepted topology and grounded requirements to `SpecIR`

The other four roles use instruction-tuned base models with
chemical-engineering-informed prompts and typed output contracts.

Three LoRA adapter release candidates have been selected for the Visual
Descriptor, Topology Agent, and Specification Agent. Their intended contents,
base-model requirements, checksums, loading examples, and release boundary are
documented in [`weights/README.md`](weights/README.md).

The adapter binaries are not committed to ordinary Git history. After the
remaining metadata, license, integrity, and secret-scan checks pass, they are
planned as versioned GitHub Release assets. Training code and reproducible
configuration files will be packaged separately, with their release status
stated explicitly.

## OpenIDAES-450

OpenIDAES-450 is being organized and audited as a companion benchmark for
equation-oriented chemical-process simulation. A public release is planned
after documentation, provenance, licensing and redistribution, split
integrity, privacy, and secret-scan checks are complete.

No OpenIDAES-450 dataset record is included in the initial architecture-only
demo.

## Planned public demo

The first public package is intentionally narrow. It is planned to contain:

- the seven-role architecture and conditional graph;
- typed artifact names and role I/O contracts;
- deterministic validation and fail-closed control invariants;
- the visibility and evaluator boundary; and
- a static, read-only architecture viewer with a package audit script.

It will not contain benchmark requests, source diagrams, training examples,
model outputs, topology or specification records, solver results, evaluator
references, manuscript metrics, credentials, or API controls.

## Scope

CRAFTS targets process families and simulator capabilities covered by its
verified equation-oriented modeling surface. The project does not claim
unrestricted process-model generation. Executable-model acceptance requires
structural, thermodynamic, numerical, and solver checks; a plausible textual or
graphical flowsheet alone is not treated as a successful result.

## Citation

The manuscript citation and archival identifier will be added after the public
preprint record is finalized.

## License

See [LICENSE](LICENSE). Dataset, model-weight, and third-party asset terms will
be documented separately before their respective releases.
