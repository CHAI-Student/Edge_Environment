let isProcessing = false;

function getProcessing() {
  return isProcessing;
}

function setProcessing(v) {
  isProcessing = v;
}

export default { getProcessing, setProcessing };