(() => {
  const siteUrl = document.currentScript?.dataset.siteUrl;
  if (!siteUrl || window.location.protocol !== 'https:') return;

  // Only count the published site; local and alternate preview hosts stay untracked.
  if (window.location.hostname !== new URL(siteUrl).hostname) return;

  const script = document.createElement('script');
  script.src = 'https://busuanzi.ibruce.info/busuanzi/2.3/busuanzi.pure.mini.js';
  script.async = true;
  document.head.appendChild(script);
})();
