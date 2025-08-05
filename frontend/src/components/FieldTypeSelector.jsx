import { useState, useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import ReactDOM from 'react-dom';
import '../styles/FieldTypeSelector.css';

// Field type options with their icons/labels
const FIELD_TYPES = [
  { id: 'text', label: 'Text Field', icon: '✏️' },
  { id: 'email', label: 'Email', icon: '✉️' },
  { id: 'number', label: 'Number', icon: '🔢' },
  { id: 'textarea', label: 'Text Area', icon: '📝' },
  { id: 'select', label: 'Select Dropdown', icon: '🔽' },
  { id: 'radio', label: 'Radio Button Choice', icon: '⭕' },
  { id: 'checkbox', label: 'Checkbox', icon: '✅' },
  { id: 'date', label: 'Date', icon: '📅' },
  { id: 'phone_number', label: 'Phone Number', icon: '📞' },
  { id: 'file', label: 'File Upload', icon: '📎' },
  { id: 'rating', label: 'Rating', icon: '⭐' }
];

/**
 * FieldTypeSelector Component
 * 
 * A modal popup that allows users to select a field type for adding or editing form fields.
 * 
 * @param {boolean} isOpen - Whether the modal is visible
 * @param {function} onClose - Function to call when the modal should close
 * @param {function} onSelectFieldType - Function to call when a field type is selected
 * @param {string} mode - Either 'add' or 'edit' to determine the behavior and title
 * @param {object} currentField - The current field data if in edit mode
 */
function FieldTypeSelector({ isOpen, onClose, onSelectFieldType, mode = 'add', currentField = null }) {
  const [selectedType, setSelectedType] = useState(currentField?.type || null);
  const modalRef = useRef(null);

  useEffect(() => {
    // Reset selected type when modal opens/changes
    if (isOpen) {
      setSelectedType(currentField?.type || null);
      // Prevent body scrolling when modal is open
      document.body.style.overflow = 'hidden';
      document.documentElement.style.overflow = 'hidden';
      document.body.classList.add('modal-open');
      
      // Temporarily add novalidate to the form to prevent browser tooltips
      const forms = document.querySelectorAll('form');
      forms.forEach(form => {
        form.setAttribute('data-original-novalidate', form.noValidate);
        form.setAttribute('novalidate', '');
      });
    } else {
      // Restore body scrolling when modal is closed
      document.body.style.overflow = '';
      document.documentElement.style.overflow = '';
      document.body.classList.remove('modal-open');
      
      // Restore form validation
      const forms = document.querySelectorAll('form');
      forms.forEach(form => {
        const originalNoValidate = form.getAttribute('data-original-novalidate');
        if (originalNoValidate === 'false') {
          form.removeAttribute('novalidate');
        }
        form.removeAttribute('data-original-novalidate');
      });
      
      // Clear any visible field error messages when popup closes
      const fieldErrors = document.querySelectorAll('.field-error');
      fieldErrors.forEach(error => {
        error.style.display = 'none';
      });
      
      // Dispatch a custom event to notify App component to clear validation errors
      window.dispatchEvent(new CustomEvent('clearValidationErrors'));
    }

    // Handle click outside to close modal
    function handleClickOutside(event) {
      if (modalRef.current && !modalRef.current.contains(event.target)) {
        onClose();
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      // Ensure we restore scrolling when component unmounts
      document.body.style.overflow = '';
      document.documentElement.style.overflow = '';
      document.body.classList.remove('modal-open');
      
      // Restore form validation on cleanup
      const forms = document.querySelectorAll('form');
      forms.forEach(form => {
        const originalNoValidate = form.getAttribute('data-original-novalidate');
        if (originalNoValidate === 'false') {
          form.removeAttribute('novalidate');
        }
        form.removeAttribute('data-original-novalidate');
      });
    };
  }, [isOpen, onClose, currentField]);

  const handleSelectType = (typeId) => {
    setSelectedType(typeId);
    onSelectFieldType(typeId);
    onClose();
  };

  // If the modal is not open, don't render anything
  if (!isOpen) return null;
  const modalContent = (
    <div className="field-selector-overlay">
      <div className="field-selector-modal" ref={modalRef}>
        <div className="field-selector-header">
          <h3>{mode === 'add' ? 'Select from below' : 'Change field type'}</h3>
          <button className="close-button" onClick={onClose}>×</button>
        </div>
        <div className="field-selector-content">
          <div className="field-type-grid">
            {FIELD_TYPES.map((type) => (
              <button
                key={type.id}
                className={`field-type-button ${selectedType === type.id ? 'selected' : ''}`}
                onClick={() => handleSelectType(type.id)}
              >
                <span className="field-type-icon">{type.icon}</span>
                <span className="field-type-label">{type.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
  return ReactDOM.createPortal(modalContent, document.body);
}

FieldTypeSelector.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  onSelectFieldType: PropTypes.func.isRequired,
  mode: PropTypes.oneOf(['add', 'edit']),
  currentField: PropTypes.object
};

export default FieldTypeSelector;
