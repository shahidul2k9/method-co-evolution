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
        StringColumn methodTypeColumn = StringColumn.create("method_type");
        StringColumn methodNameColumn = StringColumn.create("method_name");
        IntColumn startLineColumn = IntColumn.create("start_line");
        IntColumn endLineColumn = IntColumn.create("end_line");
        StringColumn urlColumn = StringColumn.create("url");
        StringColumn fileColumn = StringColumn.create("file");
        StringColumn pkgColumn = StringColumn.create("pkg");
        StringColumn fqnColumn = StringColumn.create("fqn");
        StringColumn hashColumn = StringColumn.create("hash");
        StringColumn parserColumn = StringColumn.create("parser");
//        IntColumn invocationLineColumn = IntColumn.create("invocation_line");
//        IntColumn lastAssertionLineColumn = IntColumn.create("last_assertion_line");

        for (Method jm : methods) {
            if (jm.getRepositoryName() == null) repoNameColumn.appendMissing();
            else repoNameColumn.append(jm.getRepositoryName());

            if (jm.getMethodType() == null) methodTypeColumn.appendMissing();
            else methodTypeColumn.append(jm.getMethodType());

            if (jm.getName() == null) methodNameColumn.appendMissing();
            else methodNameColumn.append(jm.getName());

            if (jm.getStartLine() == null) startLineColumn.appendMissing();
            else startLineColumn.append(jm.getStartLine());

            if (jm.getEndLine() == null) endLineColumn.appendMissing();
            else endLineColumn.append(jm.getEndLine());

            if (jm.getUrl() == null) urlColumn.appendMissing();
            else urlColumn.append(jm.getUrl());

            if (jm.getFile() == null) fileColumn.appendMissing();
            else fileColumn.append(jm.getFile());

            if (jm.getPkg() == null) pkgColumn.appendMissing();
            else pkgColumn.append(jm.getPkg());

            if (jm.getFqn() == null) fqnColumn.appendMissing();
            else fqnColumn.append(jm.getFqn());

            if (jm.getHash() == null) hashColumn.appendMissing();
            else hashColumn.append(jm.getHash());

            parserColumn.append("javaparser");

//            if (jm.getInvocationLine() == null) invocationLineColumn.appendMissing();
//            else invocationLineColumn.append(jm.getInvocationLine());
//
//            if (jm.getLastAssertionLine() == null) lastAssertionLineColumn.appendMissing();
//            else lastAssertionLineColumn.append(jm.getLastAssertionLine());
        }

        Table table = Table.create("methods")
                .addColumns(
                        repoNameColumn,
                        methodNameColumn,
                        urlColumn,
                        methodTypeColumn,
                        startLineColumn,
                        endLineColumn,
                        pkgColumn,
                        fqnColumn,
                        fileColumn,
                        hashColumn,
                        parserColumn
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
        StringColumn fromPkgColumn = StringColumn.create("from_pkg");
        StringColumn fromFqnColumn = StringColumn.create("from_fqn");
        IntColumn fromInvocationLineColumn = IntColumn.create("from_invocation");
        IntColumn fromLastCallBeforeAnAssertion = IntColumn.create("from_lcba");



        StringColumn toMethodNameColumn = StringColumn.create("to_name");
        IntColumn toMethodStartLineColumn = IntColumn.create("to_start");
        IntColumn toMethodEndLineColumn = IntColumn.create("to_end");
        StringColumn toMethodFileColumn = StringColumn.create("to_file");
        StringColumn toMethodUrlColumn = StringColumn.create("to_url");
        StringColumn toMethodPkgColumn = StringColumn.create("to_pkg");
        StringColumn toMethodFqnColumn = StringColumn.create("to_fqn");
        IntColumn  toInvocationLineColumn = IntColumn.create("to_invocation");
        IntColumn toLastCallBeforeAnAssertion = IntColumn.create("to_lcba");



        StringColumn repositoryNameColumn = StringColumn.create("project");
        StringColumn commitHashColumn = StringColumn.create("hash");


        List<Column<?>> allColumns = new ArrayList<>();
        allColumns.add(repositoryNameColumn);

        allColumns.add(fromMethodNameColumn);
        allColumns.add(toMethodNameColumn);

        allColumns.add(fromMethodUrlColumn);
        allColumns.add(toMethodUrlColumn);



        allColumns.add(fromPkgColumn);
        allColumns.add(toMethodPkgColumn);

        allColumns.add(fromFqnColumn);
        allColumns.add(toMethodFqnColumn);

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

        allColumns.add(commitHashColumn);
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
                fromFqnColumn.append(from.getFqn());
                fromLastCallBeforeAnAssertion.append(from.getLcba());


                toMethodNameColumn.append(to.getName());
                toMethodStartLineColumn.append(to.getStartLine());
                toMethodEndLineColumn.append(to.getEndLine());
                toMethodFileColumn.append(to.getFile());
                toMethodUrlColumn.append(to.getUrl());
                toMethodPkgColumn.append(to.getPkg());
                toMethodFqnColumn.append(to.getFqn());
                toLastCallBeforeAnAssertion.append(to.getLcba());

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