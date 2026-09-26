# Stage 4 Optimization

Stage 4 starts from a converged Stage-3 steady-state model and turns selected
fixed operating specifications into decision variables.

For the HDA distillation reference, this follows the official IDAES continuation:

- add heating, cooling, operating-cost, and reactor-capital-cost expressions;
- minimize operating plus capital cost;
- unfix bounded decision variables;
- constrain distillate production, distillate purity, and F101 benzene overhead loss.

Current implementation:

- `run_hda_reference_optimization.py` - local HDA distillation optimization target.

Run from `langgraph_idaes_pipeline/`:

```bash
/scratch/e1518147/vanda_pypkg/envs/py310/bin/python \
  stage4_optimization/run_hda_reference_optimization.py \
  --report validation/VectorEngine_qwen36_validation/web_HDA_distillation_case_20260530_211532/hda_reference_optimization_report.json
```
