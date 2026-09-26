# OpenIDAES-450 case collection

The 450-case demo package is available in the [openidaes450-demo-2026-09-26 release](https://github.com/Galigeigei-Z/CRAFTS-Multi-agent-for-Equation-oriented-PSE/releases/tag/openidaes450-demo-2026-09-26).

- [Download the complete archive](https://github.com/Galigeigei-Z/CRAFTS-Multi-agent-for-Equation-oriented-PSE/releases/download/openidaes450-demo-2026-09-26/OpenIDAES-450-demo.tar.gz)
- [Browse all 450 case descriptions, specifications and results](CASE_INDEX.md)
- [Guidelines for reproducing and inspecting cases](REPRODUCING_AND_INSPECTING.md)
- [Detailed setup and usage](SETUP_AND_USAGE.md)
- [450-case CSV catalog](catalog.csv) · [JSON catalog](catalog.json)
- [Runtime and package records](environment/README.md)
- [Citation and acknowledgments](THIRD_PARTY_NOTICES.md)

This directory contains browsable folders for all 450 cases, catalogs, guides, split and environment records.
Python entry points and selected runner sources are included for every case;
shared source dependencies are under `sources/`, with `run_case.py` as the launcher.
The archive also includes the local HTML browser and 39 package wheels. Extract it and open
`OpenIDAES-450-demo/index.html`. Use the extracted directory for the offline package-installation commands. With
a compatible environment already installed, cases can also run from this directory.

| Model type | Cases |
|---|---:|
| Native IDAES | 237 |
| Original reduced models | 163 |
| New reduced demonstrations | 11 |
| Grid optimization | 21 |
| Design optimization | 17 |
| EXPOsan dynamic model | 1 |
| **Total** | **450** |

Each case records its model type, implementation scope, computed values and solver
evidence. See [model scope and validation](MODEL_SCOPE.md) for the interpretation
of the model families, numerical checks and reproduction coverage. Follow the [setup guide](SETUP_AND_USAGE.md) for package installation,
solver configuration and external source/data requirements.

If you find OpenIDAES-450 useful, please cite our paper, [CRAFTS: Collaborative Role-Adaptive Fine-Tuning of LLM Agents for Chemical Process Simulation](https://arxiv.org/abs/2608.01369), and acknowledge the IDAES project.
