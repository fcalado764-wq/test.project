// Animações de entrada dos cards
document.addEventListener('DOMContentLoaded', () => {
    const cards = document.querySelectorAll('.event-card');
    cards.forEach((card, i) => {
        card.style.opacity = '0';
        card.style.animationDelay = `${i * 0.08}s`;
        card.style.animation = `fadeInUp 0.5s ease ${i * 0.08}s forwards`;
    });

    // Smooth hover nos cards
    document.querySelectorAll('.event-card').forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.style.transition = 'transform 0.25s ease, box-shadow 0.25s ease';
        });
    });
});
