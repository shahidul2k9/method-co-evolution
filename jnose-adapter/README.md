# jnose-adapter

Executable wrapper around [`jnose-core`](https://github.com/arieslab/jnose-core) for the MHC `test-smell` workflow.

`jnose-core` is a library jar and cannot be run directly with `java -jar`. This adapter provides the command-line entry point expected by MHC:

```bash
java -jar jnose-adapter-1.0.0.jar --file <input.csv> --output <output.csv>
```

## Build Steps

Run these commands from the project root unless noted otherwise.

1. Confirm the `jnose-core` checkout exists:

   ```bash
   ls -d jnose-core
   ```

2. Install `jnose-core` into the local Maven repository if it is not already installed:

   ```bash
   cd jnose-core
   mvn -q install
   cd ..
   ```

3. Build the adapter:

   ```bash
   cd jnose-adapter
   mvn -q package
   cd ..
   ```

4. Copy the executable adapter jar into the workspace jar directory:

   ```bash
   cp jnose-adapter/target/jnose-adapter-1.0.0.jar workspace/jar/jnose-adapter-1.0.0.jar
   ```

5. Run the MHC test-smell workflow:

   ```bash
   mhc test-smell \
       --workspace-directory "workspace" \
       --repository-directory "workspace/repository" \
       --jar-directory "workspace/jar" \
       --tool-name jnose \
       --stage all \
       --callgraph-dir callgraph \
       --project "commons-io"
   ```

After step 4, `workspace/jar/jnose-adapter-1.0.0.jar` is the executable jar that MHC discovers for `--tool-name jnose`.
