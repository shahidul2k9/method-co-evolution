# Artifact Detection

Method Parser stores artifact classification as additive tags in one `artifact`
column. Tags are encoded by prefixing each tag with `#` and separating tags
with one space:

```text
#production-code
#test-code #test-unit #test-method
#test-module #test-code #test-unit #test-fixture
#test-module #test-code #test-utility
#test-code #test-resource
```

Use helpers instead of equality checks:

```java
ArtifactTags.hasTag(artifact, "test-method")
```

```python
has_tag(artifact, "test-method")
```

## Tags

| Tag | Meaning |
| --- | --- |
| `test-module` | Code lives in a module whose purpose is testing. |
| `test-code` | Broad test-related code. |
| `test-method` | Actual test method; replacement for the old `artifact=test`. |
| `test-fixture` | Setup/teardown method such as `@BeforeEach` or `setUp()`. |
| `test-utility` | Test-related helper method that is not a test method or fixture. |
| `test-unit` | Unit-test source root. |
| `test-integration` | Integration-test source root. |
| `test-resource` | Test resource/data file; skipped by scanners. |
| `production-resource` | Production resource/data file; skipped by scanners. |
| `test-generated` | Generated test-related source. |
| `production-generated` | Generated production source. |
| `production-code` | Normal production source code. |

`test-method`, `test-fixture`, and `test-utility` are mutually exclusive for a
single method.

## Config

Artifact detection reads a YAML file or all `.yml` / `.yaml` files in a
directory:

```text
config/artifact-detection/
  defaults.yml
  jgit.yml
  lucene.yml
  spring-boot.yml
  intellij-community.yml
```

Rules can be declared globally, per project, and per module:

```yaml
defaults:
  mainSourceRoots:
    - src/main/java
  unitTestSourceRoots:
    - src/test/java
  testResourceRoots:
    - src/test/resources

projects:
  jgit:
    testModulePatterns:
      - "*.test"
    modules:
      org.eclipse.jgit.test:
        mainSourceRoots:
          - src
        unitTestSourceRoots:
          - tst
        integrationTestSourceRoots:
          - exttst
        testResourceRoots:
          - tst-rsrc
```

Detection precedence is:

```text
1. YAML config
2. Build metadata: Maven, Gradle, Ant, IntelliJ .iml, .idea/modules.xml, Eclipse .classpath
3. Built-in conventions
4. Package-derived source-root inference
5. Module-name test pattern
```

## Examples

JGit:

```text
org.eclipse.jgit.test/src helper method
=> #test-module #test-code #test-utility

org.eclipse.jgit.test/tst @Test method
=> #test-module #test-code #test-unit #test-method

org.eclipse.jgit.test/exttst @Test method
=> #test-module #test-code #test-integration #test-method

org.eclipse.jgit.test/tst-rsrc file
=> #test-module #test-code #test-resource
```

IntelliJ:

```text
testSrc method
=> #test-code #test-unit #test-utility or #test-code #test-unit #test-method

testGen method
=> #test-code #test-generated #test-utility

testData file
=> #test-code #test-resource
```

## CLI

Fresh scans accept an artifact config path:

```bash
mhc method-scan \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --repository-directory "$ME_WORKSPACE_DIRECTORY/repository" \
  --data-directory "$ME_WORKSPACE_DIRECTORY/data" \
  --jar-directory "$ME_WORKSPACE_DIRECTORY/jar" \
  --artifact-config-path "$ME_WORKSPACE_DIRECTORY/config/artifact-detection" \
  --project jgit \
  --replace
```

Update existing method/class CSV files without rescanning callgraphs:

```bash
mhc artifact-update \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --repository-directory "$ME_WORKSPACE_DIRECTORY/repository" \
  --data-directory "$ME_WORKSPACE_DIRECTORY/data" \
  --jar-directory "$ME_WORKSPACE_DIRECTORY/jar" \
  --artifact-config-path "$ME_WORKSPACE_DIRECTORY/config/artifact-detection" \
  --project jgit \
  --target method,class \
  --backup
```

Artifact update classifies files and parses Java method declarations with the
Java artifact detector to detect `test-method`, `test-fixture`, and
`test-utility`; it does not rebuild signatures, resolve symbols, or regenerate
callgraphs.

With `--backup`, the previous CSV is saved beside the original as
`bk_<project>.csv`, for example `data/method/bk_jgit.csv`.
