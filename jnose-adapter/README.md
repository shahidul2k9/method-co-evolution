# jnose-adapter

Executable wrapper around [`jnose-core`](https://github.com/arieslab/jnose-core) for the `mhc test-smell` workflow.

`jnose-core` is a library JAR and cannot be run directly with `java -jar`. This adapter provides the command-line entry point that MHC expects:

```bash
java -jar jnose-adapter-1.0.0.jar --file <input.csv> --output <output.csv>
```

## Build Order

Run all commands from the repository root.

1. Confirm the `jnose-core` checkout exists:

   ```bash
   ls -d jnose-core
   ```

2. Install `jnose-core` into the local Maven repository:

   ```bash
   cd jnose-core
   mvn -q install
   cd ..
   ```

3. Build the executable adapter:

   ```bash
   cd jnose-adapter
   mvn -q package
   cd ..
   ```

4. Copy the adapter JAR into the shared workspace JAR directory:

   ```bash
   mkdir -p "$ME_WORKSPACE_DIRECTORY/jar"
   cp jnose-adapter/target/jnose-adapter-1.0.0.jar \
     "$ME_WORKSPACE_DIRECTORY/jar/jnose-adapter-1.0.0.jar"
   ```

After this step, `mhc test-smell --tool-name jnose` discovers the executable JAR from:

```text
WORKSPACE_DIRECTORY/jar/jnose-adapter-1.0.0.jar
```

## MHC Usage

Generate method and callgraph data first, then run:

```bash
mhc test-smell \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --jar-directory "$ME_WORKSPACE_DIRECTORY/jar" \
  --tool-name jnose \
  --stage all \
  --callgraph-dir callgraph \
  --project "commons-io"
```

The workflow reads experiment data from:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/method/<project>.csv
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/callgraph/<project>.csv
```

and writes intermediate files under `.test-smell/jnose/` plus final normalized output under `test-smell/jnose/` in the same experiment directory.
