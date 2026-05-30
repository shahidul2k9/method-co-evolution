package mhc.jnose;

import br.ufba.jnose.core.Config;
import br.ufba.jnose.core.JNoseCore;
import br.ufba.jnose.dto.TestClass;
import br.ufba.jnose.dto.TestSmell;
import br.ufba.jnose.core.testsmelldetector.testsmell.AbstractSmell;
import br.ufba.jnose.core.testsmelldetector.testsmell.SmellyElement;
import br.ufba.jnose.core.testsmelldetector.testsmell.TestFile;
import br.ufba.jnose.core.testsmelldetector.testsmell.TestSmellDetector;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.Logger;

public class JNoseAdapter {
    private static final String[] HEADER = {
            "projectName",
            "name",
            "pathFile",
            "productionFile",
            "junitVersion",
            "loc",
            "qtdMethods",
            "testSmellName",
            "testSmellMethod",
            "testSmellLineBegin",
            "testSmellLineEnd",
            "methodNameHash",
            "methodNameFullHash",
            "methodCode",
            "methodCodeHash",
            "FullHash"
    };

    public static void main(String[] args) throws Exception {
        disableJnoseLogging();
        Map<String, String> options = parseOptions(args);
        String input = options.get("--file");
        String output = options.get("--output");
        if (input == null || output == null) {
            throw new IllegalArgumentException("Usage: java -jar jnose-adapter.jar --file <input.csv> --output <output.csv>");
        }
        System.setErr(new PrintStream(OutputStream.nullOutputStream()));

        Config config = allSmellsConfig();
        JNoseCore core = new JNoseCore(config, Runtime.getRuntime().availableProcessors());
        TestSmellDetector detector = TestSmellDetector.createTestSmellDetector(config);
        List<InputRow> rows = readInput(Path.of(input));
        Path outputPath = Path.of(output);
        if (outputPath.getParent() != null) {
            Files.createDirectories(outputPath.getParent());
        }

        try (BufferedWriter writer = Files.newBufferedWriter(outputPath, StandardCharsets.UTF_8)) {
            writeCsvLine(writer, HEADER);
            for (InputRow row : rows) {
                writeDetectedSmells(writer, core, detector, row);
            }
        }
    }

    private static void writeDetectedSmells(
            BufferedWriter writer,
            JNoseCore core,
            TestSmellDetector detector,
            InputRow row
    ) throws IOException {
        TestClass testClass = new TestClass();
        testClass.setProjectName(row.appName);
        testClass.setPathFile(row.pathToTestFile);
        testClass.setProductionFile(row.pathToProductionFile);
        testClass.setJunitVersion(TestClass.JunitVersion.None);
        testClass.setNumberLine(0);
        testClass.setNumberMethods(0);

        try {
            core.isTestFile(testClass);
            if (testClass.getName() == null || testClass.getName().isEmpty()) {
                testClass.setName(simpleClassName(row.pathToTestFile));
            }
            if (testClass.getFullName() == null || testClass.getFullName().isEmpty()) {
                testClass.setFullName(testClass.getName());
            }
            detectSmells(detector, testClass);
        } catch (Exception exception) {
            return;
        }

        for (TestSmell smell : testClass.getListTestSmell()) {
            String range = value(smell.getRange());
            writeCsvLine(
                    writer,
                    new String[]{
                            value(testClass.getProjectName()),
                            value(testClass.getName()),
                            value(testClass.getPathFile()),
                            value(testClass.getProductionFile()),
                            value(testClass.getJunitVersion()),
                            value(testClass.getNumberLine()),
                            value(testClass.getNumberMethods()),
                            value(smell.getName()),
                            value(smell.getMethod()),
                            range,
                            range,
                            value(smell.getMethodNameHash()),
                            value(smell.getMethodNameFullURIHash()),
                            "",
                            "",
                            ""
                    }
            );
        }
    }

    private static void detectSmells(TestSmellDetector detector, TestClass testClass) {
        TestFile testFile = new TestFile(
                testClass.getProjectName(),
                testClass.getPathFile(),
                testClass.getProductionFile(),
                testClass.getNumberLine(),
                testClass.getNumberMethods()
        );
        try {
            TestFile detected = detector.detectSmells(testFile);
            for (AbstractSmell smell : detected.getTestSmells()) {
                if (smell == null) {
                    continue;
                }
                for (SmellyElement element : smell.getSmellyElements()) {
                    if (element.getHasSmell()) {
                        TestSmell testSmell = new TestSmell();
                        testSmell.setName(smell.getSmellName());
                        testSmell.setMethod(element.getElementName());
                        testSmell.setRange(element.getRange());
                        testSmell.setTestClass(testClass);
                        testClass.getListTestSmell().add(testSmell);
                    }
                }
            }
        } catch (Exception exception) {
            return;
        }
        setLineSumTestSmells(testClass);
    }

    private static void setLineSumTestSmells(TestClass testClass) {
        Map<String, Integer> counts = new HashMap<>();
        for (TestSmell smell : testClass.getListTestSmell()) {
            counts.put(smell.getName(), counts.getOrDefault(smell.getName(), 0) + 1);
        }
        testClass.setLineSumTestSmells(counts);
    }

    private static List<InputRow> readInput(Path input) throws IOException {
        List<InputRow> rows = new ArrayList<>();
        try (BufferedReader reader = Files.newBufferedReader(input, StandardCharsets.UTF_8)) {
            String line;
            boolean first = true;
            while ((line = reader.readLine()) != null) {
                if (line.trim().isEmpty()) {
                    continue;
                }
                List<String> fields = parseCsvLine(line, ',');
                if (first && !fields.isEmpty() && "appName".equals(fields.get(0))) {
                    first = false;
                    continue;
                }
                first = false;
                if (fields.size() < 3) {
                    continue;
                }
                rows.add(new InputRow(fields.get(0), fields.get(1), fields.get(2)));
            }
        }
        return rows;
    }

    private static Map<String, String> parseOptions(String[] args) {
        Map<String, String> options = new LinkedHashMap<>();
        for (int index = 0; index < args.length; index++) {
            String arg = args[index];
            if (arg.startsWith("--") && index + 1 < args.length) {
                options.put(arg, args[++index]);
            }
        }
        return options;
    }

    private static List<String> parseCsvLine(String line, char delimiter) {
        List<String> fields = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        boolean quoted = false;
        for (int index = 0; index < line.length(); index++) {
            char ch = line.charAt(index);
            if (ch == '"') {
                if (quoted && index + 1 < line.length() && line.charAt(index + 1) == '"') {
                    current.append('"');
                    index++;
                } else {
                    quoted = !quoted;
                }
            } else if (ch == delimiter && !quoted) {
                fields.add(current.toString());
                current.setLength(0);
            } else {
                current.append(ch);
            }
        }
        fields.add(current.toString());
        return fields;
    }

    private static void writeCsvLine(BufferedWriter writer, String[] fields) throws IOException {
        for (int index = 0; index < fields.length; index++) {
            if (index > 0) {
                writer.write(';');
            }
            writer.write(escape(fields[index]));
        }
        writer.newLine();
    }

    private static String escape(String value) {
        String text = value(value);
        if (text.contains(";") || text.contains("\"") || text.contains("\n") || text.contains("\r")) {
            return "\"" + text.replace("\"", "\"\"") + "\"";
        }
        return text;
    }

    private static String value(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private static String simpleClassName(String path) {
        String normalized = path.replace('\\', '/');
        int slash = normalized.lastIndexOf('/');
        String file = slash >= 0 ? normalized.substring(slash + 1) : normalized;
        int dot = file.lastIndexOf('.');
        return dot >= 0 ? file.substring(0, dot) : file;
    }

    private static Config allSmellsConfig() {
        return new Config() {
            public Boolean assertionRoulette() { return true; }
            public Boolean conditionalTestLogic() { return true; }
            public Boolean constructorInitialization() { return true; }
            public Boolean defaultTest() { return true; }
            public Boolean dependentTest() { return true; }
            public Boolean duplicateAssert() { return true; }
            public Boolean eagerTest() { return true; }
            public Boolean emptyTest() { return true; }
            public Boolean exceptionCatchingThrowing() { return true; }
            public Boolean generalFixture() { return true; }
            public Boolean mysteryGuest() { return true; }
            public Boolean printStatement() { return true; }
            public Boolean redundantAssertion() { return true; }
            public Boolean sensitiveEquality() { return true; }
            public Boolean verboseTest() { return true; }
            public Boolean sleepyTest() { return true; }
            public Boolean lazyTest() { return true; }
            public Boolean unknownTest() { return true; }
            public Boolean ignoredTest() { return true; }
            public Boolean resourceOptimism() { return true; }
            public Boolean magicNumberTest() { return true; }
            public Integer maxStatements() { return 30; }
        };
    }

    private static void disableJnoseLogging() {
        Logger root = Logger.getLogger("");
        root.setLevel(Level.OFF);
        for (Handler handler : root.getHandlers()) {
            handler.setLevel(Level.OFF);
        }
        Logger.getLogger("br.ufba.jnose").setLevel(Level.OFF);
    }

    private static class InputRow {
        private final String appName;
        private final String pathToTestFile;
        private final String pathToProductionFile;

        private InputRow(String appName, String pathToTestFile, String pathToProductionFile) {
            this.appName = appName;
            this.pathToTestFile = pathToTestFile;
            this.pathToProductionFile = pathToProductionFile;
        }
    }
}
