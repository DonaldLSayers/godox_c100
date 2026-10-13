// Post-analysis export: decompiled C for every function, plus a string index
// listing which functions use each string. Arg: output directory.
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.listing.DataIterator;
import java.io.File;
import java.io.PrintWriter;
import java.util.Set;
import java.util.TreeSet;

public class ExportDecomp extends GhidraScript {
    @Override
    public void run() throws Exception {
        File out = new File(getScriptArgs()[0]);
        out.mkdirs();

        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        int ok = 0, failed = 0;
        try (PrintWriter w = new PrintWriter(new File(out, "c100.c"))) {
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                if (monitor.isCancelled()) break;
                DecompileResults r = di.decompileFunction(f, 60, monitor);
                w.printf("// ===== %s @ 0x%s =====%n", f.getName(), f.getEntryPoint());
                if (r.decompileCompleted()) {
                    w.println(r.getDecompiledFunction().getC());
                    ok++;
                } else {
                    w.println("// decompile failed: " + r.getErrorMessage());
                    failed++;
                }
            }
        }
        di.dispose();

        try (PrintWriter w = new PrintWriter(new File(out, "strings.tsv"))) {
            w.println("address\tstring\tused_by");
            DataIterator it = currentProgram.getListing().getDefinedData(true);
            while (it.hasNext()) {
                Data d = it.next();
                if (!d.hasStringValue()) continue;
                Set<String> users = new TreeSet<>();
                for (Reference ref : getReferencesTo(d.getAddress())) {
                    Function f = getFunctionContaining(ref.getFromAddress());
                    if (f != null) users.add(f.getName());
                }
                String s = String.valueOf(d.getValue()).replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r");
                w.printf("0x%s\t%s\t%s%n", d.getAddress(), s, String.join(", ", users));
            }
        }
        println(String.format("exported %d functions (%d failed) to %s", ok, failed, out));
    }
}
