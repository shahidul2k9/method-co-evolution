# method-parser

Java 21 / Maven module that extracts Java methods, classes, and call graphs with JavaParser. The resulting CSV datasets are consumed by `mhc` and downstream co-evolution pipelines.

## Requirements

- Java 21. The module is compiled with `--release 21`.
- Maven 3.6+.

On HPC or Slurm environments, load Java and Maven before building:

```bash
module load java/21.0.1
module load maven
mvn -version
```

On a local machine, install Java 21 and Maven with your package manager and confirm both are on `PATH`.

## Build

From the repository root:

```bash
cd method-parser
mvn clean install -DskipTests
cd ..
```

The Maven build writes a fat JAR under `method-parser/target/`. The helper script builds the module and copies the executable JAR into the shared workspace JAR directory:

```bash
scripts/build-method-parser.sh
```

`mhc method-scan`, `mhc class-scan`, `mhc method-callgraph`, and `mhc method-complexity` resolve the parser JAR from:

```text
WORKSPACE_DIRECTORY/jar/
```

or from the explicit `--jar-directory` value.

## Experiment Outputs

Parser-backed `mhc` commands write datasets under:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/
```

The main outputs are:

| Dataset | Producer | Purpose |
|---------|----------|---------|
| `method/<project>.csv` | `mhc method-scan` | Method and constructor index |
| `class/<project>.csv` | `mhc class-scan` | Class/type boundary used by artifact detection and fallback resolution |
| `callgraph/<project>.csv` | `mhc method-callgraph` | Fan-out call edges, usually test-to-production candidates |
| `fanin/<project>.csv` | `mhc method-callgraph` | Reverse call edges, usually production-to-test candidates |
| `method-complexity/<project>.csv` | `mhc method-complexity` | Per-method complexity metrics |

## `method/<project>.csv`

One row per method or constructor extracted from the repository at the indexed commit.

| Column | Type | Description |
|--------|------|-------------|
| `project` | string | Repository name |
| `name` | string | Simple method or constructor name |
| `url` | string | GitHub blob URL with file and line anchor |
| `artifact` | string | Artifact role, such as test or production |
| `start_line` | int | First line of the method body |
| `end_line` | int | Last line of the method body |
| `expression` | string | `method` or `constructor` |
| `pkg` | string | Java package name |
| `fqn` | string | Fully-qualified name, such as `Class#method` |
| `fqs` | string | Fully-qualified signature with fully-qualified parameter types; varargs use `...` |
| `tctracer_fqs` | string | TCTracer-style signature with simple declared parameter type names; varargs use `[]` |
| `testlinker_fqs` | string | In declared method rows, identical to `tctracer_fqs` |
| `testlinker_fqp` | string | JSON array of fully-qualified parameter types; varargs use `[]` |
| `file` | string | Relative Java source path |
| `abstract` | int | `1` when abstract, else `0` |
| `parser` | string | Parser implementation, normally `javaparser` |
| `resolver` | string | Symbol resolver strategy |
| `hash` | string | Git commit hash used for the index |

The `url` column is the primary method identifier used throughout the pipeline.

## `class/<project>.csv`

One row per indexed class or type declaration. The class dataset is the type boundary for callgraph fallback resolution and artifact role updates.

Typical fields include project, class name, package, fully-qualified name, source file, line range, artifact role, parser/resolver metadata, and commit hash. Treat this file as authoritative when JavaParser and scanner naming differ for inner or anonymous classes.

## `callgraph/<project>.csv` and `fanin/<project>.csv`

One row per directed call edge. `callgraph/` records what a method calls. `fanin/` records the reverse direction. Both files share the same schema.

| Column | Type | Description |
|--------|------|-------------|
| `project` | string | Repository name |
| `from_name` / `to_name` | string | Simple method names |
| `from_url` / `to_url` | string | GitHub blob URLs |
| `from_expression` / `to_expression` | string | `method` or `constructor` |
| `from_pkg` / `to_pkg` | string | Java package names |
| `from_fqn` / `to_fqn` | string | Fully-qualified names |
| `from_fqs` / `to_fqs` | string | Fully-qualified signatures |
| `from_tctracer_fqs` / `to_tctracer_fqs` | string | TCTracer-style declared signatures |
| `from_testlinker_fqs` / `to_testlinker_fqs` | string | TestLinker-style signatures |
| `from_testlinker_fqp` / `to_testlinker_fqp` | string | JSON arrays of fully-qualified parameter types |
| `from_start` / `from_end` | int | Calling method line range |
| `to_start` / `to_end` | int | Called method line range |
| `from_invocation` | int | Source line of the call in `callgraph/` |
| `from_lcba` / `to_lcba` | int | Last call before assertion line number |
| `from_file` / `to_file` | string | Relative source file paths |
| `from_caller_url` / `to_caller_url` | string | Caller URL for deep call chains |
| `from_call_depth` / `to_call_depth` | int | Depth in the call chain |
| `hash` | string | Git commit hash |
| `from_resolver` / `to_resolver` | string | Symbol resolver strategy |

Important signature distinction:

- `to_tctracer_fqs` is derived from the called method declaration.
- `to_testlinker_fqs` is derived from actual argument types at the call site when available. It may contain `null`, `<UNKNOWN>`, or a resolved argument type.
- `from_testlinker_fqs` is identical to `from_tctracer_fqs` because the calling method is a declaration context.

## JavaParser Fallback Resolution

When JavaParser cannot resolve a call, the callgraph generator uses a CSV-bounded fallback. The fallback requires both:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/method/<project>.csv
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/class/<project>.csv
```

The class CSV defines the complete type boundary, and the method CSV defines the complete callable boundary. A fallback edge is emitted only when the target method exists in the method CSV and its declaring class exists in the class CSV. External or unindexed methods, such as `java.lang.Object` methods, are not emitted unless they are present in those CSVs.

Fallback matching uses generic method identity fields such as `fqn`, `fqs`, `name`, `expression`, `pkg`, `file`, `start_line`, `end_line`, and `url`. TCTracer and TestLinker signatures are output metadata and are not used to select a fallback target.

The resolver infers the owner from call syntax such as `obj.m()`, `this.m()`, unscoped `m()`, `Type.m()`, or `new Type(...)`, then searches class CSV owners in this order:

1. Exact inferred class.
2. Nearest subclasses or implementors, closest first.
3. Nearest superclasses or interfaces, closest first.

Within the same class-distance level, known arity mismatches are rejected, then the best `fqn`/`fqs` match is selected. Remaining ties are resolved by CSV order so generation remains deterministic. Generic type arguments are erased before owner/signature comparison.
