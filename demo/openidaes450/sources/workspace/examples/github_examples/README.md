# Current-tree official example dependencies

`clones/examples` is an isolated shallow clone of the official
`https://github.com/IDAES/examples-pse.git` repository. It is runtime source
input for official IDAES reference runners in this 2026-07-23 tree; it is not a
legacy artifact binding and must not be replaced by files from the 2026-05-31
tree.

The dependency is frozen by `dependency_snapshot.json`, including the Git
commit and SHA-256 hashes of the NGCC source and initialization files consumed
by the native runners.
