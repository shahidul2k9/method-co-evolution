package rnd.method.parser.call.graph.util;

import rnd.method.parser.call.graph.model.ClassMapping;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.model.MethodCall;
import rnd.method.parser.call.graph.util.MethodParserUtil;
import tech.tablesaw.api.IntColumn;
import tech.tablesaw.api.StringColumn;
import tech.tablesaw.api.Table;
import tech.tablesaw.columns.Column;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class TableUtil {

    public static void toTable(List<Method> methods, String outputPath) {
        StringColumn repoNameColumn = StringColumn.create("project");
        StringColumn artifactColumn = StringColumn.create("artifact");
        StringColumn methodNameColumn = StringColumn.create("name");
        IntColumn startLineColumn = IntColumn.create("start_line");
        IntColumn endLineColumn = IntColumn.create("end_line");
        StringColumn urlColumn = StringColumn.create("url");
        StringColumn expressionColumn = StringColumn.create("expression");
        StringColumn fileColumn = StringColumn.create("file");
        StringColumn pkgColumn = StringColumn.create("pkg");
        StringColumn fqnColumn = StringColumn.create("fqn");
        StringColumn fqsColumn = StringColumn.create("fqs");
        StringColumn tcTracerFqsColumn = StringColumn.create("tctracer_fqs");
        StringColumn testlinkerFqsColumn = StringColumn.create("testlinker_fqs");
        StringColumn testlinkerFqpColumn = StringColumn.create("testlinker_fqp");
        IntColumn abstractColumn = IntColumn.create("abstract");
        StringColumn resolverColumn = StringColumn.create("resolver");
        StringColumn hashColumn = StringColumn.create("hash");
        StringColumn parserColumn = StringColumn.create("parser");
//        IntColumn invocationLineColumn = IntColumn.create("invocation_line");
//        IntColumn lastAssertionLineColumn = IntColumn.create("last_assertion_line");

        for (Method m : methods) {
            if (m.getRepositoryName() == null) repoNameColumn.appendMissing();
            else repoNameColumn.append(m.getRepositoryName());

            if (m.getArtifact() == null) artifactColumn.appendMissing();
            else artifactColumn.append(m.getArtifact());

            if (m.getName() == null) methodNameColumn.appendMissing();
            else methodNameColumn.append(m.getName());

            if (m.getStartLine() == null) startLineColumn.appendMissing();
            else startLineColumn.append(m.getStartLine());

            if (m.getEndLine() == null) endLineColumn.appendMissing();
            else endLineColumn.append(m.getEndLine());

            if (m.getUrl() == null) urlColumn.appendMissing();
            else urlColumn.append(m.getUrl());

            if (m.getFile() == null) fileColumn.appendMissing();
            else fileColumn.append(m.getFile());

            if (m.getPkg() == null) pkgColumn.appendMissing();
            else pkgColumn.append(m.getPkg());

            if (m.getFqn() == null) fqnColumn.appendMissing();
            else fqnColumn.append(m.getFqn());

            if (m.getFqs() == null) fqsColumn.appendMissing();
            else fqsColumn.append(m.getFqs());

            if (m.getTcTracerFqs() == null) tcTracerFqsColumn.appendMissing();
            else tcTracerFqsColumn.append(m.getTcTracerFqs());

            if (m.getTestlinkerFqs() == null) testlinkerFqsColumn.appendMissing();
            else testlinkerFqsColumn.append(m.getTestlinkerFqs());

            if (m.getTestlinkerFqp() == null) testlinkerFqpColumn.appendMissing();
            else testlinkerFqpColumn.append(m.getTestlinkerFqp());

            if (m.getAbstractMethod() == null) abstractColumn.appendMissing();
            else abstractColumn.append(m.getAbstractMethod());

            if (m.getResolver() == null) resolverColumn.appendMissing();
            else resolverColumn.append(m.getResolver());

            if (m.getHash() == null) hashColumn.appendMissing();
            else hashColumn.append(m.getHash());

            if (m.getExpression() == null) expressionColumn.appendMissing();
            else expressionColumn.append(m.getExpression());

            parserColumn.append("javaparser");

//            if (m.getInvocationLine() == null) invocationLineColumn.appendMissing();
//            else invocationLineColumn.append(m.getInvocationLine());
//
//            if (m.getLastAssertionLine() == null) lastAssertionLineColumn.appendMissing();
//            else lastAssertionLineColumn.append(m.getLastAssertionLine());
        }

        Table table = Table.create("method")
                .addColumns(
                        repoNameColumn,
                        methodNameColumn,
                        urlColumn,
                        artifactColumn,
                        startLineColumn,
                        endLineColumn,
                        expressionColumn,
                        pkgColumn,
                        fqnColumn,
                        fqsColumn,
                        tcTracerFqsColumn,
                        testlinkerFqsColumn,
                        testlinkerFqpColumn,
                        fileColumn,
                        abstractColumn,
                        parserColumn,
                        resolverColumn,
                        hashColumn
//                        ,
//                        invocationLineColumn,
//                        lastAssertionLineColumn
                );
        boolean mkdirs = new File(outputPath).getParentFile().mkdirs();
        table.write().csv(outputPath);
    }

    public static void toTable(List<MethodCall> methodCalls, String outputPath, boolean isFanOut) {

        StringColumn fromMethodNameColumn = StringColumn.create("from_name");
        IntColumn fromMethodStartLineColumn = IntColumn.create("from_start");
        IntColumn fromMethodEndLineColumn = IntColumn.create("from_end");
        StringColumn fromMethodFileColumn = StringColumn.create("from_file");
        StringColumn fromMethodUrlColumn = StringColumn.create("from_url");
        StringColumn fromExpressionColumn = StringColumn.create("from_expression");
        StringColumn fromPkgColumn = StringColumn.create("from_pkg");
        StringColumn fromFqnColumn = StringColumn.create("from_fqn");
        StringColumn fromFqsColumn = StringColumn.create("from_fqs");
        StringColumn fromTcTracerFqsColumn = StringColumn.create("from_tctracer_fqs");
        StringColumn fromTestlinkerFqsColumn = StringColumn.create("from_testlinker_fqs");
        StringColumn fromTestlinkerFqpColumn = StringColumn.create("from_testlinker_fqp");
        StringColumn fromResolverColumn = StringColumn.create("from_resolver");
        IntColumn fromInvocationLineColumn = IntColumn.create("from_invocation");
        IntColumn fromLastCallBeforeAnAssertion = IntColumn.create("from_lcba");
        StringColumn fromCallerUrlColumn = StringColumn.create("from_caller_url");
        IntColumn fromCallDepthColumn = IntColumn.create("from_call_depth");



        StringColumn toMethodNameColumn = StringColumn.create("to_name");
        IntColumn toMethodStartLineColumn = IntColumn.create("to_start");
        IntColumn toMethodEndLineColumn = IntColumn.create("to_end");
        StringColumn toMethodFileColumn = StringColumn.create("to_file");
        StringColumn toMethodUrlColumn = StringColumn.create("to_url");
        StringColumn toExpressionColumn = StringColumn.create("to_expression");
        StringColumn toMethodPkgColumn = StringColumn.create("to_pkg");
        StringColumn toFqnColumn = StringColumn.create("to_fqn");
        StringColumn toFqsColumn = StringColumn.create("to_fqs");
        StringColumn toTcTracerFqsColumn = StringColumn.create("to_tctracer_fqs");
        StringColumn toTestlinkerFqsColumn = StringColumn.create("to_testlinker_fqs");
        StringColumn toTestlinkerFqpColumn = StringColumn.create("to_testlinker_fqp");
        StringColumn toResolverColumn = StringColumn.create("to_resolver");
        IntColumn  toInvocationLineColumn = IntColumn.create("to_invocation");
        IntColumn toLastCallBeforeAnAssertion = IntColumn.create("to_lcba");
        StringColumn toCallerUrlColumn = StringColumn.create("to_caller_url");
        IntColumn toCallDepthColumn = IntColumn.create("to_call_depth");


        StringColumn repositoryNameColumn = StringColumn.create("project");
        StringColumn commitHashColumn = StringColumn.create("hash");


        List<Column<?>> allColumns = new ArrayList<>();
        allColumns.add(repositoryNameColumn);

        allColumns.add(fromMethodNameColumn);
        allColumns.add(toMethodNameColumn);

        allColumns.add(fromMethodUrlColumn);
        allColumns.add(toMethodUrlColumn);


        allColumns.add(fromExpressionColumn);
        allColumns.add(toExpressionColumn);



        allColumns.add(fromPkgColumn);
        allColumns.add(toMethodPkgColumn);

        allColumns.add(fromFqnColumn);
        allColumns.add(toFqnColumn);


        allColumns.add(fromFqsColumn);
        allColumns.add(fromTcTracerFqsColumn);
        allColumns.add(fromTestlinkerFqsColumn);
        allColumns.add(fromTestlinkerFqpColumn);

        allColumns.add(toFqsColumn);
        allColumns.add(toTcTracerFqsColumn);
        allColumns.add(toTestlinkerFqsColumn);
        allColumns.add(toTestlinkerFqpColumn);

        allColumns.add(fromMethodStartLineColumn);
        allColumns.add(fromMethodEndLineColumn);

        allColumns.add(toMethodStartLineColumn);
        allColumns.add(toMethodEndLineColumn);



        allColumns.add(fromInvocationLineColumn);
        allColumns.add(toInvocationLineColumn);

        allColumns.add(fromLastCallBeforeAnAssertion);
        allColumns.add(toLastCallBeforeAnAssertion);

        allColumns.add(fromMethodFileColumn);
        allColumns.add(toMethodFileColumn);

        allColumns.add(fromCallerUrlColumn);
        allColumns.add(toCallerUrlColumn);

        allColumns.add(fromCallDepthColumn);
        allColumns.add(toCallDepthColumn);
        allColumns.add(commitHashColumn);
        allColumns.add(fromResolverColumn);
        allColumns.add(toResolverColumn);
        Table table = Table.create(allColumns);
        for (MethodCall mc : methodCalls) {
            Method one = mc.getMethod();
            List<Method> manyMethods = mc.getFanMethods().isEmpty()? Collections.singletonList(Method.builder().build()) : mc.getFanMethods();
            for (Method many : manyMethods) {

                Method from = isFanOut ? one : many;
                Method to = isFanOut ? many : one;


                repositoryNameColumn.append(from.getRepositoryName());
                commitHashColumn.append(from.getHash());


                fromMethodNameColumn.append(from.getName());
                fromMethodStartLineColumn.append(from.getStartLine());
                fromMethodEndLineColumn.append(from.getEndLine());
                fromMethodFileColumn.append(from.getFile());
                fromMethodUrlColumn.append(from.getUrl());
                fromPkgColumn.append(from.getPkg());
                fromLastCallBeforeAnAssertion.append(from.getLcba());


                toMethodNameColumn.append(to.getName());
                toMethodStartLineColumn.append(to.getStartLine());
                toMethodEndLineColumn.append(to.getEndLine());
                toMethodFileColumn.append(to.getFile());
                toMethodUrlColumn.append(to.getUrl());
                toMethodPkgColumn.append(to.getPkg());
                toLastCallBeforeAnAssertion.append(to.getLcba());

                fromFqnColumn.append(from.getFqn());
                toFqnColumn.append(to.getFqn());

                fromFqsColumn.append(from.getFqs());
                toFqsColumn.append(to.getFqs());

                fromTcTracerFqsColumn.append(from.getTcTracerFqs());
                toTcTracerFqsColumn.append(to.getTcTracerFqs());

                fromTestlinkerFqsColumn.append(from.getTestlinkerFqs());
                toTestlinkerFqsColumn.append(to.getTestlinkerFqs());

                fromTestlinkerFqpColumn.append(from.getTestlinkerFqp());
                toTestlinkerFqpColumn.append(to.getTestlinkerFqp());

                fromResolverColumn.append(from.getResolver());
                toResolverColumn.append(to.getResolver());

                fromExpressionColumn.append(from.getExpression());
                toExpressionColumn.append(to.getExpression());

                fromCallerUrlColumn.appendMissing();
                toCallerUrlColumn.appendMissing();

                fromCallDepthColumn.appendMissing();
                toCallDepthColumn.appendMissing();
                if (isFanOut){
                    fromInvocationLineColumn.append(to.getInvocationLine());
                    toInvocationLineColumn.appendMissing();
                }else {
                    fromInvocationLineColumn.appendMissing();
                    toInvocationLineColumn.appendMissing();
                }
            }
        }
        boolean mkdirs = new File(outputPath).getParentFile().mkdirs();
        table.write().csv(outputPath);
    }

    public static void saveCallgraph(List<MethodCall> callgraphList, String fanOutOutputFile, String fanInOutputFile) {
        toTable(callgraphList, new File(fanOutOutputFile).getAbsolutePath(), true);
        List<MethodCall> fanInList = MethodParserUtil.fanInFromFanOut(callgraphList);
        toTable(fanInList, new File(fanInOutputFile).getAbsolutePath(), false);
    }

    public static void toClassTable(List<ClassMapping> classes, String outputPath) {
        StringColumn projectColumn      = StringColumn.create("project");
        StringColumn nameColumn         = StringColumn.create("name");
        StringColumn fqnColumn          = StringColumn.create("fqn");
        StringColumn pkgColumn          = StringColumn.create("pkg");
        StringColumn fileColumn         = StringColumn.create("file");
        StringColumn urlColumn          = StringColumn.create("url");
        IntColumn startLineColumn       = IntColumn.create("start_line");
        IntColumn endLineColumn         = IntColumn.create("end_line");
        StringColumn expressionColumn   = StringColumn.create("expression");
        StringColumn artifactColumn     = StringColumn.create("artifact");
        IntColumn abstractColumn        = IntColumn.create("abstract");
        StringColumn parentNamesColumn  = StringColumn.create("parent_names");
        StringColumn parentFqnsColumn   = StringColumn.create("parent_fqns");
        StringColumn hashColumn         = StringColumn.create("hash");

        for (ClassMapping c : classes) {
            projectColumn.append(c.getRepositoryName());
            nameColumn.append(c.getName());

            if (c.getFqn() == null)       fqnColumn.appendMissing();
            else                          fqnColumn.append(c.getFqn());

            if (c.getPkg() == null)       pkgColumn.appendMissing();
            else                          pkgColumn.append(c.getPkg());

            if (c.getFile() == null)      fileColumn.appendMissing();
            else                          fileColumn.append(c.getFile());

            if (c.getUrl() == null)       urlColumn.appendMissing();
            else                          urlColumn.append(c.getUrl());

            if (c.getStartLine() == null) startLineColumn.appendMissing();
            else                          startLineColumn.append(c.getStartLine());

            if (c.getEndLine() == null)   endLineColumn.appendMissing();
            else                          endLineColumn.append(c.getEndLine());

            if (c.getExpression() == null) expressionColumn.appendMissing();
            else                           expressionColumn.append(c.getExpression());

            if (c.getArtifact() == null)  artifactColumn.appendMissing();
            else                          artifactColumn.append(c.getArtifact());

            if (c.getAbstractClass() == null) abstractColumn.appendMissing();
            else                              abstractColumn.append(c.getAbstractClass());

            if (c.getParentNames() == null) parentNamesColumn.appendMissing();
            else                            parentNamesColumn.append(c.getParentNames());

            if (c.getParentFqns() == null)  parentFqnsColumn.appendMissing();
            else                            parentFqnsColumn.append(c.getParentFqns());

            if (c.getHash() == null)      hashColumn.appendMissing();
            else                          hashColumn.append(c.getHash());
        }

        Table table = Table.create("class")
                .addColumns(
                        projectColumn, nameColumn, fqnColumn, pkgColumn,
                        fileColumn, urlColumn, startLineColumn, endLineColumn,
                        expressionColumn, artifactColumn, abstractColumn,
                        parentNamesColumn, parentFqnsColumn,
                        hashColumn
                );
        new File(outputPath).getParentFile().mkdirs();
        table.write().csv(outputPath);
    }
}
