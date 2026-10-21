'use strict';

// Existing API Gateway endpoint: keep this unchanged unless your API changes.
const FEEDBACK_API_URL = 'https://mpsx121rhf.execute-api.us-east-1.amazonaws.com/prod/submit';

const form = document.getElementById('feedbackForm');
const submitButton = form.querySelector('button[type="submit"]');
const fileInput = document.getElementById('file');
const fileName = document.getElementById('fileName');
const messageInput = document.getElementById('message');
const messageCount = document.getElementById('messageCount');
const modal = document.getElementById('myModal');
const modalMessage = document.getElementById('modalMessage');
const modalOkayButton = document.getElementById('modalOkayButton');
const closeModalButton = document.querySelector('.close-modal');
const responseMessage = document.getElementById('responseMessage');

messageInput.addEventListener('input', () => {
  messageCount.textContent = `${messageInput.value.length} / 10000`;
});

fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  fileName.textContent = file ? file.name : 'Choose a file to transmit';
  responseMessage.textContent = '';
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (submitButton.disabled) return;

  const name = document.getElementById('name').value.trim();
  const email = document.getElementById('email').value.trim();
  const message = messageInput.value.trim();
  const file = fileInput.files[0];
  responseMessage.textContent = '';

  if (!name || !email || !message) {
    showModal('Please complete all required fields.');
    return;
  }

  if (file) {
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      showModal('Please select a PDF file.');
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      showModal('PDF must be 4 MB or smaller.');
      return;
    }
  }

  submitButton.disabled = true;
  submitButton.querySelector('.button-label').textContent = 'TRANSMITTING...';

  try {
    let file_base64 = null;
    if (file) file_base64 = await readFileAsBase64(file);

    const response = await fetch(FEEDBACK_API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, message, file_base64 })
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || `Request failed with status ${response.status}`);

    showModal(data.message || 'Feedback submitted successfully.');
    form.reset();
    messageCount.textContent = '0 / 10000';
    fileName.textContent = 'Choose a file to transmit';
  } catch (error) {
    console.error('Feedback submission error:', error);
    const messageText = error.message && !error.message.includes('Failed to fetch')
      ? error.message
      : 'Transmission failed. Please check your connection and try again.';
    responseMessage.textContent = messageText;
    showModal(messageText);
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector('.button-label').textContent = 'TRANSMIT FEEDBACK';
  }
});

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== 'string' || !result.includes(',')) {
        reject(new Error('Could not read the selected PDF.'));
        return;
      }
      resolve(result.split(',')[1]);
    };
    reader.onerror = () => reject(new Error('Failed to read the selected PDF.'));
    reader.readAsDataURL(file);
  });
}

function showModal(message) {
  modalMessage.textContent = message;
  modal.classList.add('is-open');
  modalOkayButton.focus();
}

function closeModal() {
  modal.classList.remove('is-open');
}

modalOkayButton.addEventListener('click', closeModal);
closeModalButton.addEventListener('click', closeModal);
modal.addEventListener('click', (event) => {
  if (event.target === modal) closeModal();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && modal.classList.contains('is-open')) closeModal();
});
