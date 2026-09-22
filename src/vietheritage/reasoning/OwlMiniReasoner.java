import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import org.apache.jena.Jena;
import org.apache.jena.rdf.model.InfModel;
import org.apache.jena.rdf.model.Model;
import org.apache.jena.rdf.model.ModelFactory;
import org.apache.jena.rdf.model.RDFList;
import org.apache.jena.rdf.model.RDFNode;
import org.apache.jena.reasoner.ReasonerRegistry;
import org.apache.jena.reasoner.ValidityReport;
import org.apache.jena.riot.RDFDataMgr;
import org.apache.jena.riot.RDFFormat;
import org.apache.jena.vocabulary.OWL;
import org.apache.jena.vocabulary.OWL2;
import org.apache.jena.vocabulary.RDF;

/** Local, source-file-launched adapter; no server or network access is needed. */
class OwlMiniReasoner {
    public static void main(String[] args) throws Exception {
        Path statusPath = Path.of(args[2]);
        if (!"4.10.0".equals(Jena.VERSION)) {
            Files.writeString(statusPath,
                "JENA_VERSION_MISMATCH\nExpected 4.10.0, found " + Jena.VERSION,
                StandardCharsets.UTF_8);
            System.exit(1);
        }

        // A plain model does not resolve owl:imports or dereference RDF IRIs.
        Model asserted = RDFDataMgr.loadModel(Path.of(args[0]).toUri().toString());
        Model input = ModelFactory.createDefaultModel().add(asserted);
        // AX-004: OWL Mini implements OWL 1 disjointWith, not OWL 2 AllDisjointClasses.
        // Expand only this equivalent form; AX-008/AX-009 validation is separate.
        asserted.listResourcesWithProperty(RDF.type, OWL2.AllDisjointClasses)
            .forEachRemaining(group -> {
                List<RDFNode> members = group.getRequiredProperty(OWL2.members)
                    .getResource().as(RDFList.class).asJavaList();
                for (int i = 0; i < members.size(); i++) {
                    for (int j = i + 1; j < members.size(); j++) {
                        input.add(members.get(i).asResource(), OWL.disjointWith, members.get(j));
                    }
                }
            });

        InfModel inference = ModelFactory.createInfModel(ReasonerRegistry.getOWLMiniReasoner(), input);
        inference.prepare();
        ValidityReport validity = inference.validate();
        List<String> status = new ArrayList<>();
        status.add(validity.isValid() ? "PASS" : "ONTOLOGY_INCONSISTENT");
        validity.getReports().forEachRemaining(report -> status.add(report.toString()));
        if (!validity.isValid()) {
            Files.write(statusPath, status, StandardCharsets.UTF_8);
            System.exit(2);
        }

        // Enumerate the InfModel, including backward-rule answers, rather than
        // getDeductionsModel(), which only exposes materialized deductions.
        Model delta = inference.difference(asserted);
        delta.setNsPrefixes(asserted.getNsPrefixMap());
        try (OutputStream output = Files.newOutputStream(Path.of(args[1]))) {
            RDFDataMgr.write(output, delta, RDFFormat.TURTLE_PRETTY);
        }
        Files.write(statusPath, status, StandardCharsets.UTF_8);
    }
}
