function confirmAction(hint, targetUrl) {
  if (confirm(hint)) {
    location.href = targetUrl;
  }
}