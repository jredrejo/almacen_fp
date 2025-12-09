document.addEventListener('DOMContentLoaded', function() {
    // Mobile navigation toggle
    const navToggle = document.querySelector('.nav-toggle');
    const navMenu = document.querySelector('.nav-menu');
    const navLinks = document.querySelectorAll('.nav-link');

    // Toggle mobile menu
    navToggle.addEventListener('click', function() {
        navMenu.classList.toggle('active');

        // Animate hamburger menu
        const bars = navToggle.querySelectorAll('.bar');
        bars.forEach((bar, index) => {
            if (navMenu.classList.contains('active')) {
                if (index === 0) bar.style.transform = 'rotate(-45deg) translate(-5px, 6px)';
                if (index === 1) bar.style.opacity = '0';
                if (index === 2) bar.style.transform = 'rotate(45deg) translate(-5px, -6px)';
            } else {
                bar.style.transform = '';
                bar.style.opacity = '';
            }
        });
    });

    // Close mobile menu when clicking on a link
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            navMenu.classList.remove('active');

            // Reset hamburger menu
            const bars = navToggle.querySelectorAll('.bar');
            bars.forEach(bar => {
                bar.style.transform = '';
                bar.style.opacity = '';
            });
        });
    });

    // Smooth scrolling for navigation links
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            const href = this.getAttribute('href');

            // Check if it's an internal link
            if (href.startsWith('#')) {
                e.preventDefault();
                const targetId = href.substring(1);
                const targetSection = document.getElementById(targetId);

                if (targetSection) {
                    const headerHeight = document.querySelector('.header').offsetHeight;
                    const targetPosition = targetSection.offsetTop - headerHeight - 20;

                    window.scrollTo({
                        top: targetPosition,
                        behavior: 'smooth'
                    });
                }
            }
        });
    });

    // Header background on scroll
    window.addEventListener('scroll', function() {
        const header = document.querySelector('.header');
        if (window.scrollY > 100) {
            header.style.boxShadow = '0 2px 20px rgba(0,0,0,0.1)';
        } else {
            header.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
        }
    });

    // Animate elements on scroll
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);

    // Observe all cards and sections
    const animatedElements = document.querySelectorAll(
        '.objetivo-card, .timeline-item, .resultado-item, .doc-card, .metric-card'
    );

    animatedElements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(el);
    });

    // Gallery image lazy loading effect
    const galleryItems = document.querySelectorAll('.gallery-item img');

    const imageObserver = new IntersectionObserver(function(entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;

                // Función para mostrar la imagen
                const showImage = () => {
                    img.style.transition = 'opacity 0.5s ease';
                    img.style.opacity = '1';
                };

                // Verificar si la imagen ya está cargada
                if (img.complete && img.naturalHeight !== 0) {
                    showImage();
                } else {
                    img.onload = showImage;
                    img.onerror = function() {
                        // En caso de error, mostrar igualmente el espacio
                        console.warn(`No se pudo cargar la imagen: ${img.src}`);
                        img.style.opacity = '0.3'; // Semi-transparente para indicar error
                    };

                    // Fallback por si onload no se dispara
                    setTimeout(() => {
                        if (img.style.opacity === '0') {
                            showImage();
                        }
                    }, 500);
                }

                imageObserver.unobserve(img);
            }
        });
    });

    galleryItems.forEach(img => {
        // No iniciar con opacidad 0 para evitar el parpadeo
        // En su lugar, añadimos una clase CSS para el efecto
        img.classList.add('gallery-image-loading');
        imageObserver.observe(img);
    });

    // Active navigation highlighting
    const sections = document.querySelectorAll('section[id]');

    window.addEventListener('scroll', function() {
        let current = '';

        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.clientHeight;
            const headerHeight = document.querySelector('.header').offsetHeight;

            if (window.scrollY >= (sectionTop - headerHeight - 100)) {
                current = section.getAttribute('id');
            }
        });

        navLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === `#${current}`) {
                link.classList.add('active');
            }
        });
    });

    // Modal functionality for gallery images
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImage');
    const modalCaption = document.getElementById('modalCaption');
    const closeModal = document.querySelector('.modal-close');
    const modalPrev = document.querySelector('.modal-prev');
    const modalNext = document.querySelector('.modal-next');

    // Get all gallery images
    const galleryImages = document.querySelectorAll('.gallery-item img');
    let currentImageIndex = 0;

    // Add click event to each gallery image
    galleryImages.forEach((img, index) => {
        img.style.cursor = 'pointer'; // Add pointer cursor to indicate clickable
        img.addEventListener('click', function() {
            modal.style.display = 'block';
            modalImg.src = this.src;
            currentImageIndex = index;

            // Get the caption from the gallery caption
            const caption = this.parentElement.querySelector('.gallery-caption');
            if (caption) {
                modalCaption.textContent = caption.textContent;
            } else {
                modalCaption.textContent = '';
            }

            // Prevent scrolling when modal is open
            document.body.style.overflow = 'hidden';
        });
    });

    // Navigation functions
    function showImage(index) {
        if (index >= 0 && index < galleryImages.length) {
            currentImageIndex = index;
            modalImg.src = galleryImages[index].src;
            
            // Update caption
            const caption = galleryImages[index].parentElement.querySelector('.gallery-caption');
            if (caption) {
                modalCaption.textContent = caption.textContent;
            } else {
                modalCaption.textContent = '';
            }
        }
    }

    function showNextImage() {
        let nextIndex = currentImageIndex + 1;
        if (nextIndex >= galleryImages.length) {
            nextIndex = 0; // Loop back to first image
        }
        showImage(nextIndex);
    }

    function showPrevImage() {
        let prevIndex = currentImageIndex - 1;
        if (prevIndex < 0) {
            prevIndex = galleryImages.length - 1; // Loop to last image
        }
        showImage(prevIndex);
    }

    // Event listeners for navigation
    modalNext.addEventListener('click', function(e) {
        e.stopPropagation(); // Prevent modal from closing
        showNextImage();
    });

    modalPrev.addEventListener('click', function(e) {
        e.stopPropagation(); // Prevent modal from closing
        showPrevImage();
    });

    // Keyboard navigation
    document.addEventListener('keydown', function(e) {
        if (modal.style.display === 'block') {
            if (e.key === 'Escape') {
                closeModalFunc();
            } else if (e.key === 'ArrowRight') {
                showNextImage();
            } else if (e.key === 'ArrowLeft') {
                showPrevImage();
            }
        }
    });

    // Close modal when clicking the X
    closeModal.addEventListener('click', function() {
        closeModalFunc();
    });

    // Close modal when clicking outside the image
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeModalFunc();
        }
    });

    // Function to close modal
    function closeModalFunc() {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto'; // Restore scrolling
    }
});

// Add active link style dynamically
const style = document.createElement('style');
style.textContent = `
    .nav-link.active {
        color: #3498db !important;
        position: relative;
    }
    .nav-link.active::after {
        content: '';
        position: absolute;
        bottom: -5px;
        left: 0;
        right: 0;
        height: 2px;
        background: #3498db;
    }
`;
document.head.appendChild(style);