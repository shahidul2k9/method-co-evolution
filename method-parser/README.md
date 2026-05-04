# method-parser

Java 21 / Maven module that extracts methods and call graphs from Java source using JavaParser. Produces CSV datasets consumed by the `mhc` CLI.

## Build

```bash
cd method-parser
mvn clean install -DskipTests
```

The fat JAR is written to `target/method-parser-*.jar`. The helper script builds and copies it to the cache in one step:

```bash
scripts/build-method-parser.sh   # copies JAR to <ME_CACHE_DIRECTORY>/jar/
```

The `mhc method-scan` and `mhc method-callgraph` commands resolve the JAR from `--jar-directory` at runtime.

## Datasets

### `data/method/{project}.csv` — method index

One row per method or constructor extracted from the repository at the indexed commit.

| Column | Type | Description |
|--------|------|-------------|
| `project` | string | Repository name |
| `name` | string | Simple method or constructor name |
| `url` | string | GitHub blob URL (file + line anchor) |
| `artifact` | string | `test` or `production` |
| `start_line` | int | First line of the method body |
| `end_line` | int | Last line of the method body |
| `expression` | string | `method` or `constructor` |
| `pkg` | string | Java package name |
| `fqn` | string | Fully-qualified name (`Class#method`) |
| `fqs` | string | Fully-qualified signature: fully-qualified param types, varargs as `...` (e.g. `IOUtils.closeQuietly(java.io.Closeable...)`) |
| `tctracer_fqs` | string | TCTracer-style FQS: simple (unqualified) **declared** param type names, varargs as `[]` (e.g. `IOUtils.closeQuietly(Closeable[])`) |
| `testlinker_fqs` | string | In the method index (declared methods) this is identical to `tctracer_fqs`. See call-graph note below for the distinction in called-method context. |
| `testlinker_fqp` | string | TestLinker parameter list as a JSON array of fully-qualified type names, varargs as `[]` (e.g. `["java.io.Closeable[]"]`). In the method index this is derived from the declared param types. |
| `file` | string | Relative path to the Java source file |
| `abstract` | int | `1` if the method is abstract, else `0` |
| `parser` | string | Always `javaparser` |
| `resolver` | string | Symbol resolver strategy used |
| `hash` | string | Git commit hash the index was built from |

The `url` column is the primary key used throughout the pipeline to identify methods.

### `data/callgraph/{project}.csv` — callgraph / fan-out (test → production calls)

One row per directed call edge. `callgraph` files record what a method calls (formerly fan-out); `fanin` files record what calls a method. Both share the same schema.

| Column | Type | Description |
|--------|------|-------------|
| `project` | string | Repository name |
| `from_name` / `to_name` | string | Simple method name |
| `from_url` / `to_url` | string | GitHub blob URL of the method |
| `from_expression` / `to_expression` | string | `method` or `constructor` |
| `from_pkg` / `to_pkg` | string | Java package |
| `from_fqn` / `to_fqn` | string | Fully-qualified name |
| `from_fqs` / `to_fqs` | string | Fully-qualified signature: fully-qualified param types, varargs as `...` |
| `from_tctracer_fqs` / `to_tctracer_fqs` | string | TCTracer-style FQS: simple **declared** param type names, varargs as `[]`. Always derived from the method declaration, not the call site. |
| `from_testlinker_fqs` / `to_testlinker_fqs` | string | TestLinker-style FQS: simple param type names, varargs as `[]`. **Key distinction from `tctracer_fqs`**: for the called method (`to_testlinker_fqs`) this is built from the **actual argument types passed at the call site**, not the declared param types. This means it can contain `null` (when a null literal is passed), `<UNKNOWN>` (when the argument type cannot be resolved), or the resolved runtime argument type. For the calling method (`from_testlinker_fqs`) it is identical to `from_tctracer_fqs`. |
| `from_testlinker_fqp` / `to_testlinker_fqp` | string | TestLinker parameter list as a JSON array of fully-qualified types, varargs as `[]`. For `to_testlinker_fqp`, argument types at the call site are used (same source as `to_testlinker_fqs`). |
| `from_start` / `from_end` | int | Line range of the `from` method |
| `to_start` / `to_end` | int | Line range of the `to` method |
| `from_invocation` | int | Line where the call appears in the `from` method (callgraph only) |
| `from_lcba` / `to_lcba` | int | Last call before an assertion (line number) |
| `from_file` / `to_file` | string | Relative source file path |
| `from_caller_url` / `to_caller_url` | string | Caller URL (populated for deep call chains) |
| `from_call_depth` / `to_call_depth` | int | Depth in the call chain |
| `hash` | string | Git commit hash |
| `from_resolver` / `to_resolver` | string | Symbol resolver strategy |

Callgraph files are stored under `data/callgraph/` after link generation. Fanin files are stored under `data/fanin/`.
