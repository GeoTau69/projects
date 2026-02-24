/* sidebar-scroll.js — IntersectionObserver scroll-spy
   Používá se v project.html.j2 (build pipeline) */

const headings = document.querySelectorAll('h2[id]');
const links    = document.querySelectorAll('.sidebar a');

const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            links.forEach(l => l.classList.remove('active'));
            const active = document.querySelector(`.sidebar a[href="#${entry.target.id}"]`);
            if (active) active.classList.add('active');
        }
    });
}, { threshold: 0.2, rootMargin: '-52px 0px -60% 0px' });

headings.forEach(h => observer.observe(h));
