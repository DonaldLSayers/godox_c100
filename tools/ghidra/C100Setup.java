// Pre-analysis setup for the C100 app image (raw ARM, loaded at 0x0).
// Marks the ARM exception vectors as functions and enables the aggressive
// instruction finder so code not reachable from the vectors is found too.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

public class C100Setup extends GhidraScript {
    @Override
    public void run() throws Exception {
        setAnalysisOption(currentProgram, "ARM Aggressive Instruction Finder", "true");
        // Vector table at 0x0 loads handler addresses from the literal pool at 0x20.
        String[] names = {"vec_reset", "vec_undef", "vec_swi", "vec_pabort", "vec_dabort", "vec_irq", "vec_fiq"};
        for (int i = 0; i < names.length; i++) {
            Address target = toAddr(getInt(toAddr(0x20 + 4 * i)) & 0xffffffffL);
            disassemble(target);
            createFunction(target, names[i]);
        }
    }
}
