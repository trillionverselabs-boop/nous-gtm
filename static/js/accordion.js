/* Accordion / Collapsible Card Logic + Copy functionality */
document.addEventListener('DOMContentLoaded', function() {
    // ===== Accordion / Collapsible Card Logic =====
    var headers = document.querySelectorAll('.accordion-header');

    headers.forEach(function(header) {
        header.addEventListener('click', function() {
            var targetId = this.getAttribute('data-accordion');
            var content = document.getElementById(targetId);
            var arrow = this.querySelector('.accordion-arrow');

            if (content.classList.contains('active')) {
                // Collapse
                content.classList.remove('active');
                content.style.maxHeight = null;
                arrow.style.transform = 'rotate(0deg)';
            } else {
                // Expand
                content.classList.add('active');
                content.style.maxHeight = content.scrollHeight + 'px';
                arrow.style.transform = 'rotate(180deg)';
            }
        });
    });

    // ===== Snapshot expand-all button =====
    var expandBtn = document.getElementById('snapshotExpandAll');
    if (expandBtn) {
        expandBtn.addEventListener('click', function() {
            var items = document.querySelectorAll('.snapshot-nav-item, .snapshot-nav-subrow');
            items.forEach(function(item) {
                item.style.display = 'inline-block';
            });
            expandBtn.style.display = 'none';
        });
    }
});

/* ===== Copy Full Posting to Clipboard ===== */
function copyFullPosting() {
    var el = document.getElementById('roleFullPosting');
    if (!el) return;

    var text = el.innerText || el.textContent;
    var textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();

    try {
        document.execCommand('copy');
        // Show temporary feedback
        var btn = document.querySelector('.btn-copy');
        var original = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(function() { btn.textContent = original; }, 2000);
    } catch (err) {
        console.error('Copy failed:', err);
    }

    document.body.removeChild(textarea);
}
