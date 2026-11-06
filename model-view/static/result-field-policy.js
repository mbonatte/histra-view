// Python result archives contain a final spring snapshot; native C# can serve every step.
export function resultFieldStepIndex(index, count, scalarRequested, nativeCsharp) {
  return scalarRequested && !nativeCsharp && count > 0 ? count - 1 : index;
}
