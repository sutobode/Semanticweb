// Local ARQ execution for CQ tests: use the named-graph union, as Fuseki does.
// Reasoning is supplied by the existing production reasoner, not this helper.
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.apache.jena.query.Dataset;
import org.apache.jena.query.QueryExecution;
import org.apache.jena.query.QueryExecutionFactory;
import org.apache.jena.query.QueryFactory;
import org.apache.jena.query.ResultSetFormatter;
import org.apache.jena.riot.RDFDataMgr;

class CqFixtureQuery {
    public static void main(String[] args) throws Exception {
        Dataset dataset = RDFDataMgr.loadDataset(args[0]);
        try {
            dataset.setDefaultModel(dataset.getUnionModel());
            for (int i = 2; i < args.length; i++) {
                Path query = Path.of(args[i]);
                Path output = Path.of(args[1], query.getFileName().toString().substring(0, 4) + ".json");
                String text = Files.readString(query, StandardCharsets.UTF_8);
                try (QueryExecution execution = QueryExecutionFactory.create(QueryFactory.create(text), dataset);
                     FileOutputStream stream = new FileOutputStream(output.toFile())) {
                    ResultSetFormatter.outputAsJSON(stream, execution.execSelect());
                }
            }
        } finally {
            dataset.close();
        }
    }
}
