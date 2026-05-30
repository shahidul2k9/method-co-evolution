# Artifact Detection

Method Parser stores artifact classification as additive tags in one `artifact`
column. Tags are encoded by prefixing each tag with `#` and separating tags
with one space:

```text
#main-code
#test-code #test-case-method
#test-module #main-code
#test-module #test-code #test-helper-method
#doc-module #main-code
```

Use helpers instead of equality checks:

```java
ArtifactTags.hasTag(artifact, "test-case-method")
```

```python
has_tag(artifact, "test-case-method")
```

## Tags

| Tag | Meaning |
| --- | --- |
| `test-module` | Module/path context whose purpose is testing. Does not imply `test-code`. |
| `doc-module` | Module/path context whose purpose is documentation. |
| `test-code` | Java code under a test source root. |
| `main-code` | Java code under a main source root. |
| `test-case-method` | Actual test method; replacement for the old `artifact=test`. |
| `test-fixture-method` | Setup/teardown method such as `@BeforeEach` or `setUp()`. |
| `test-helper-method` | Test-related helper method that is not a test method or fixture. |
| `test-resource` | Test resource/data file; skipped by scanners. |
| `main-resource` | Main resource/data file; skipped by scanners. |
| `test-code-generated` | Generated test-related source. |
| `main-code-generated` | Generated main source. |

`test-case-method`, `test-fixture-method`, and `test-helper-method` are mutually exclusive for a
single method.

`is_production(...)` is a derived predicate: it is true only when an artifact has
`main-code` and has no `test-*` or `doc-*` tags. For example,
`#test-module #main-code` is main code but not production.

## Config

Artifact detection reads a YAML file or all `.yml` / `.yaml` files in a
directory:

```text
$ME_WORKSPACE_DIRECTORY/config/artifact-detection/
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
    - src/androidTest/java
    - src/androidTest
    - src/test
    - src/tests/junit
  testResourceRoots:
    - src/test/resources
  testModulePatterns:
    - "*.test"
    - "*-tests"
    - integrationtest
    - integration-test
  docModulePatterns:
    - documentation
    - docs
  testMethodAnnotations:
    - org.junit.Test
    - org.junit.jupiter.api.Test
    - org.junit.jupiter.params.ParameterizedTest
    - net.jqwik.api.Property
    - net.jqwik.api.Example
  fixtureMethodAnnotations:
    - org.junit.Before
    - org.junit.jupiter.api.BeforeEach
    - net.jqwik.api.lifecycle.BeforeProperty
  legacyTestCaseSuperclasses:
    - junit.framework.TestCase
  legacyTestMethodNamePrefixes:
    - test
  testClassContextAnnotations:
    - org.junit.jupiter.api.extension.ExtendWith
    - org.junit.runner.RunWith
    - org.mockito.junit.jupiter.MockitoSettings
    - org.mockito.Mock
    - org.mockito.Spy

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
5. Module/path context patterns
```

### Method role rules

Method role detection runs only after the file has been classified as
`test-code`. The detector resolves annotation fully-qualified names with
JavaParser when possible; if symbol resolution fails, it falls back to explicit
imports, wildcard imports, and finally configured simple names.

Framework-specific rules:

| Framework | Test method rule |
| --- | --- |
| JUnit 5/Jupiter | Configured Jupiter test annotations are test cases when the method is not `private`. Package-private methods are valid. |
| JUnit 4 | `org.junit.Test` methods must be `public`, non-static, `void`, and have no parameters. |
| JUnit 3 | Unannotated name-based tests must be `public void test*()` and the class must directly or indirectly extend a configured legacy test superclass such as `junit.framework.TestCase`. |
| TestNG | Configured TestNG test annotations are test cases when the method is not `private`. |
| jqwik | `net.jqwik.api.Property` and `net.jqwik.api.Example` methods are test cases when not `private` and returning `void`, `boolean`, or `Boolean`. |
| Custom configured annotations | Project/module-configured annotations are accepted as test markers when the method is not `private`. |

Fixture annotations, including JUnit, TestNG, and jqwik lifecycle annotations,
produce `#test-fixture-method`. Fixture methods are never promoted to
`#test-case-method`.

Fallbacks are intentionally conservative. If `@Test` cannot be resolved to a
framework, the detector accepts it only for non-private `void` no-arg methods in
test code. If JavaParser cannot resolve JUnit 3 hierarchy, name-based detection
falls back only for `public void test*()` methods in classes named `*Test` or
`*TestCase`. This avoids marking protected or public helper methods named
`testSomething` as test cases.

Mockito and JUnit extension annotations are context annotations. They can help
explain why a class is a test class, but they are not test method annotations and
do not turn arbitrary methods into `#test-case-method`.

## Examples

JGit:

```text
org.eclipse.jgit.test/src helper method
=> #test-module #main-code

org.eclipse.jgit.test/tst @Test method
=> #test-module #test-code #test-case-method

org.eclipse.jgit.test/exttst @Test method
=> #test-module #test-code #test-case-method

org.eclipse.jgit.test/tst-rsrc file
=> #test-module #test-resource
```

Documentation module:

```text
documentation/src/main/java method
=> #doc-module #main-code

documentation/src/test/java @Test method
=> #doc-module #test-code #test-case-method
```

IntelliJ:

```text
testSrc method
=> #test-code #test-helper-method or #test-code #test-case-method

testGen method
=> #test-code #test-code-generated #test-helper-method

testData file
=> #test-resource
```

Android and Ant-style test roots:

```text
src/androidTest/java/... @Test method
=> #test-code #test-case-method

src/tests/junit/... JUnit 3 public void testFoo()
=> #test-code #test-case-method
```

jqwik:

```text
src/test/java/... @Property boolean propertyHolds()
=> #test-code #test-case-method

src/test/java/... @BeforeProperty void setUp()
=> #test-code #test-fixture-method
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
Java artifact detector to detect `test-case-method`, `test-fixture-method`, and
`test-helper-method`; it does not rebuild signatures, resolve symbols, or regenerate
callgraphs.

With `--backup`, the previous CSV is saved beside the original as
`bk_<project>.csv`, for example `data/method/bk_jgit.csv`.
