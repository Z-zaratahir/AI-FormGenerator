import { useState } from 'react';
import '../styles/CategorySelectPopup.css';

/**
 * A reusable popup component for selecting form field categories
 * @param {Object} props
 * @param {boolean} props.isOpen - Whether the popup is open or not
 * @param {Function} props.onClose - Function to call when popup is closed
 * @param {Function} props.onSelect - Function to call when a category is selected
 * @param {string} props.mode - Mode of operation: 'add' or 'edit'
 * @param {Object} props.currentField - The current field being edited (only needed in edit mode)
 */
const CategorySelectPopup = ({ isOpen, onClose, onSelect, mode = 'add', currentField = null }) => {
  // If the popup is not open, don't render anything
  if (!isOpen) return null;
  
  // Field types available for selection
  const fieldTypes = [
    { id: 'text', label: 'Text', icon: '✏️' },
    { id: 'textarea', label: 'Paragraph', icon: '📝' },
    { id: 'select', label: 'Dropdown', icon: '▼' },
    { id: 'radio', label: 'Multiple Choice', icon: '○' },
    { id: 'checkbox', label: 'Checkboxes', icon: '☑️' },
    { id: 'date', label: 'Date', icon: '📅' },
    { id: 'time', label: 'Time', icon: '⏰' },
    { id: 'rating', label: 'Rating', icon: '⭐' },
    { id: 'file', label: 'File Upload', icon: '📎' },
    { id: 'number', label: 'Number', icon: '#' },
    { id: 'email', label: 'Email', icon: '📧' },
    { id: 'phone', label: 'Phone', icon: '📞' }
  ];
  
  // Handle category selection
  const handleSelect = (fieldType) => {
    if (mode === 'add') {
      onSelect(fieldType);
    } else {
      // In edit mode, we pass the current field with the new type
      onSelect({ ...currentField, type: fieldType.id });
    }
    onClose();
  };
  
  return (
    <div className="popup-overlay">
      <div className="category-popup">
        <div className="popup-header">
          <h2>{mode === 'add' ? 'Add a question' : 'Edit question type'}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>
        
        <div className="popup-content">
          <div className="category-grid">
            {fieldTypes.map((fieldType) => (
              <div 
                key={fieldType.id} 
                className="category-item"
                onClick={() => handleSelect(fieldType)}
              >
                <span className="category-icon">{fieldType.icon}</span>
                <span className="category-label">{fieldType.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CategorySelectPopup;
