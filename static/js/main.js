// ===== NAVBAR SCROLL EFFECT =====
const navbar = document.querySelector('.navbar');
window.addEventListener('scroll', () => {
  if (window.scrollY > 50) {
    navbar.classList.add('scrolled');
  } else {
    navbar.classList.remove('scrolled');
  }
});

// ===== MOBILE MENU =====
function toggleMobileNav() {
  const navLinks = document.querySelector('.nav-links');
  const mobileToggle = document.querySelector('.mobile-toggle');
  if (navLinks) navLinks.classList.toggle('active');
  if (mobileToggle) mobileToggle.classList.toggle('active');
}

function closeMobileNav() {
  const navLinks = document.querySelector('.nav-links');
  const mobileToggle = document.querySelector('.mobile-toggle');
  if (navLinks) navLinks.classList.remove('active');
  if (mobileToggle) mobileToggle.classList.remove('active');
}

const mobileToggle = document.querySelector('.mobile-toggle');
const navLinks = document.querySelector('.nav-links');

if (mobileToggle) {
  mobileToggle.addEventListener('click', () => {
    navLinks.classList.toggle('active');
    mobileToggle.classList.toggle('active');
  });
}

// Close mobile menu on link click
document.querySelectorAll('.nav-links a').forEach(link => {
  link.addEventListener('click', () => {
    navLinks.classList.remove('active');
    if (mobileToggle) mobileToggle.classList.remove('active');
  });
});

// ===== SCROLL ANIMATIONS =====
const observerOptions = {
  threshold: 0.1,
  rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
    }
  });
}, observerOptions);

document.querySelectorAll('.animate-on-scroll').forEach(el => {
  observer.observe(el);
});

// ===== COUNTER ANIMATION =====
function animateCounter(element, target, suffix = '') {
  const duration = 2000;
  const start = 0;
  const startTime = performance.now();

  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const easeOut = 1 - Math.pow(1 - progress, 3);
    const current = Math.floor(start + (target - start) * easeOut);
    element.textContent = current.toLocaleString() + suffix;
    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }
  requestAnimationFrame(update);
}

// ===== LIVE STATS ANIMATION =====
function initCounters() {
  const statNumbers = document.querySelectorAll('[data-count]');
  const counterObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const target = parseInt(entry.target.dataset.count);
        const suffix = entry.target.dataset.suffix || '';
        animateCounter(entry.target, target, suffix);
        counterObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });

  statNumbers.forEach(el => counterObserver.observe(el));
}

// ===== PARTICLES =====
function createParticles() {
  const container = document.querySelector('.particles');
  if (!container) return;

  const particleCount = 30;
  for (let i = 0; i < particleCount; i++) {
    const particle = document.createElement('div');
    particle.classList.add('particle');
    particle.style.left = Math.random() * 100 + '%';
    particle.style.setProperty('--duration', (Math.random() * 10 + 8) + 's');
    particle.style.animationDelay = Math.random() * 10 + 's';
    particle.style.width = (Math.random() * 4 + 2) + 'px';
    particle.style.height = particle.style.width;
    container.appendChild(particle);
  }
}

// ===== PROGRESS BAR ANIMATION =====
function initProgressBars() {
  const bars = document.querySelectorAll('.progress-bar');
  const barObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const width = entry.target.dataset.width;
        entry.target.style.width = width + '%';
        barObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });

  bars.forEach(bar => {
    bar.style.width = '0%';
    barObserver.observe(bar);
  });
}

// ===== SMOOTH SCROLL =====
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function (e) {
    e.preventDefault();
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      target.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }
  });
});

// ===== TYPING EFFECT FOR HERO =====
function initTypingEffect() {
  const typingEl = document.querySelector('.typing-text');
  if (!typingEl) return;
  
  const words = ['Clan Glory', 'Guild Rank', 'Leaderboard', 'Win Rate'];
  let wordIndex = 0;
  let charIndex = 0;
  let isDeleting = false;
  
  function type() {
    const currentWord = words[wordIndex];
    if (isDeleting) {
      typingEl.textContent = currentWord.substring(0, charIndex - 1);
      charIndex--;
    } else {
      typingEl.textContent = currentWord.substring(0, charIndex + 1);
      charIndex++;
    }
    
    let delay = isDeleting ? 50 : 100;
    
    if (!isDeleting && charIndex === currentWord.length) {
      delay = 2000;
      isDeleting = true;
    } else if (isDeleting && charIndex === 0) {
      isDeleting = false;
      wordIndex = (wordIndex + 1) % words.length;
      delay = 500;
    }
    
    setTimeout(type, delay);
  }
  
  type();
}

// ===== LIVE STATS UPDATE =====
function updateLiveStats() {
  const gloryEl = document.querySelector('[data-live-glory]');
  const botsEl = document.querySelector('[data-live-bots]');
  
  if (gloryEl) {
    setInterval(() => {
      const current = parseInt(gloryEl.textContent.replace(/[^0-9]/g, '')) || 12;
      const increment = Math.floor(Math.random() * 500) + 100;
      gloryEl.textContent = '+' + (current + increment).toLocaleString() + ' M Glory';
    }, 3000);
  }
}

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
  createParticles();
  initCounters();
  initProgressBars();
  initTypingEffect();
  updateLiveStats();
});
