package rnd.method.parser.call.graph.util;

import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.model.MethodCall;
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
        StringColumn fqsAltColumn = StringColumn.create("fqs_alt");
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

            if (m.getFqsAlt() == null) fqsAltColumn.appendMissing();
            else fqsAltColumn.append(m.getFqsAlt());

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
                        fqsAltColumn,
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
        StringColumn fromFqsAltColumn = StringColumn.create("from_fqs_alt");
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
        StringColumn toFqsAltColumn = StringColumn.create("to_fqs_alt");
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
        allColumns.add(toFqsColumn);


        allColumns.add(fromFqsAltColumn);
        allColumns.add(toFqsAltColumn);

        allColumns.add(fromTestlinkerFqsColumn);
        allColumns.add(toTestlinkerFqsColumn);

        allColumns.add(fromTestlinkerFqpColumn);
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

                fromFqsAltColumn.append(from.getFqsAlt());
                toFqsAltColumn.append(to.getFqsAlt());

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
}
