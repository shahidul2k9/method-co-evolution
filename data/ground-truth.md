# Ground Truth Datasets

## RQ1 Test Method History Ground Truth

The test method history ground truth links to the [test method oracle](rqs/rq1/test-method-oracle). It contains 120 JSON oracle cases across 40 projects.

## RQ2 Ground Truth

This ground truth documents production-to-test mapping.

The ground-truth datasets are ordered below by how they extend one another. Each entry lists the source, the local data directory, the projects added by that source, and the cumulative project count.

| Order | Ground truth | Source | Added projects | Total projects | Extension |
| --- | --- | --- | --- | ---: | --- |
| 1 | [tctracer-2020](tctracer-2020/t2p-ground-truth) | White et al., [ICSE 2020](https://dl.acm.org/doi/10.1145/3377811.3380921) | [`commons-io`, `commons-lang`, `jfreechart`](tctracer-2020/project.csv) | 3 | Initial ground truth. |
| 2 | [tctracer-2020](tctracer-2020/t2p-ground-truth) + [tctracer-2022](tctracer-2022/t2p-ground-truth) | White et al., [ESE 2022](https://link.springer.com/10.1007/s10664-021-10079-1) | [`gson`](tctracer-2022/project.csv) | 4 | Extends `tctracer-2020` by 1 project. |
| 3 | [tctracer-2020](tctracer-2020/t2p-ground-truth) + [tctracer-2022](tctracer-2022/t2p-ground-truth) + [testlinker](testlinker/t2p-ground-truth) | Sun et al., [TSE 2024](https://ieeexplore.ieee.org/document/10648982/) | [`dubbo`, `jenkins`](testlinker/project.csv) | 6 | Extends the prior ground truth by 2 projects. |
| 4 | [t2plinker](t2plinker/t2p-ground-truth) | New | [`checkstyle`, `commons-io`, `commons-lang`, `elasticsearch`, `flink`, `hadoop`, `hibernate-orm`, `hibernate-search`, `intellij-community`, `javaparser`, `jetty.project`, `jgit`, `junit4`, `junit5`, `lucene`, `mockito`, `pmd`, `solr`, `spring-boot`, `spring-framework`](t2plinker/project.csv) | 20 | New ground truth. |
