import { useState, useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import EditFieldButton from './EditFieldButton';
import '../styles/FormField.css';

/**
 * FormField Component
 * 
 * Renders a form field with editing options
 * 
 * @param {object} field - The field data to render
 * @param {number} index - The index of the field in the form
 * @param {function} onUpdate - Function to call when the field is updated
 * @param {function} onDelete - Function to call when the field should be deleted
 */
function FormField({ field, index, onUpdate, onDelete }) {
  const [isEditing, setIsEditing] = useState(false);
  const [fieldLabel, setFieldLabel] = useState(field.label);
  const [fileError, setFileError] = useState('');
  const inputRef = useRef(null);
  
  const isRequired = field.validation?.required || false;
  
  // Handle click outside to save and exit edit mode
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (isEditing && inputRef.current && !inputRef.current.contains(event.target)) {
        saveLabel();
        setIsEditing(false);
      }
    };

    if (isEditing) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isEditing, fieldLabel, field.label]);
  
  // Creating a unique ID for accessibility
  const inputId = `${field.id || 'field'}-${index}`;

  const inputProps = {
    id: inputId,
    name: field.id,
    required: field.type === 'file' ? false : isRequired, // disable browser required for file
    placeholder: field.placeholder || '',
    onInvalid: field.type === 'file' ? (e) => e.preventDefault() : undefined,
    onBlur: field.type === 'file' && isRequired ? (e) => {
      if (!e.target.files.length) setFileError('Please select a file.');
      else setFileError('');
    } : undefined,
    onChange: field.type === 'file' && isRequired ? (e) => {
      if (!e.target.files.length) setFileError('Please select a file.');
      else setFileError('');
    } : undefined,
  };

  // Add min/max for number types from the validation object
  if (field.type === 'number' || field.type === 'range' || field.type === 'rating') {
    if (field.validation?.min !== undefined) inputProps.min = field.validation.min;
    if (field.validation?.max !== undefined) inputProps.max = field.validation.max;
  }

  const handleUpdateField = (updatedField) => {
    onUpdate(updatedField);
  };

  const toggleRequired = () => {
    handleUpdateField({
      ...field,
      validation: {
        ...field.validation,
        required: !isRequired
      }
    });
  };

  const saveLabel = () => {
    if (fieldLabel !== field.label) {
      handleUpdateField({
        ...field,
        label: fieldLabel
      });
    }
  };

  const toggleEditing = () => {
    if (isEditing) {
      // Save changes when exiting edit mode
      saveLabel();
    }
    setIsEditing(!isEditing);
    
    // Focus the input after state update
    if (!isEditing) {
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
          inputRef.current.select(); // Select all text for easy editing
        }
      }, 0);
    }
  };

  const handleLabelBlur = (e) => {
    // Remove the automatic blur save - we'll handle it with click outside
  };

  const handleLabelKeyDown = (e) => {
    if (e.key === 'Enter') {
      // Save and exit edit mode when pressing Enter
      saveLabel();
      setIsEditing(false);
    } else if (e.key === 'Escape') {
      // Cancel editing and revert to original label
      setFieldLabel(field.label);
      setIsEditing(false);
    }
  };

  const renderInput = () => {
    switch (field.type) {
      case 'textarea':
        return <textarea {...inputProps} rows="5" />;
      case 'select':
        return (
          <select {...inputProps}>
            <option value="">-- Please choose an option --</option>
            {field.options && field.options.map((option, idx) => (
              <option key={idx} value={option.toLowerCase().replace(/\s/g, '-')}>{option}</option>
            ))}
          </select>
        );
      case 'radio':
        return (
          <div className="radio-options">
            {field.options && field.options.map((option, idx) => (
              <label key={idx} className="radio-option">
                <input type="radio" name={inputProps.name} value={option.toLowerCase().replace(/\s/g, '-')} />
                {option}
              </label>
            ))}
          </div>
        );
      case 'checkbox':
        return <input type="checkbox" {...inputProps} />;
      case 'file':
        return <input type="file" {...inputProps} />;
      case 'date':
        return <input type="date" {...inputProps} />;
      case 'email':
        return <input type="email" {...inputProps} />;
      case 'number':
        return <input type="number" {...inputProps} />;
      case 'rating':
        return (
          <input
            type="number"
            {...inputProps}
            min={field.validation?.min ?? 1}
            max={field.validation?.max ?? 5}
            defaultValue={field.validation?.min ?? 1}
            step={1}
          />
        );
      case 'phone_number':
        return <input type="tel" {...inputProps} />;
      default:
        return <input type="text" {...inputProps} />;
    }
  };

  return (
    <div className="form-field-container">
      <div className="field-header">
        <div className="field-label-section">
          <button 
            className="edit-label-button" 
            onClick={toggleEditing}
            title={isEditing ? "Save label" : "Edit label"}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {isEditing ? (
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
              ) : (
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              )}
              {isEditing ? (
                <>
                  <polyline points="17,10 17,13 14,13"/>
                  <path d="M9 15h3l8.5-8.5a2.12 2.12 0 0 0 0-3l-1-1a2.12 2.12 0 0 0-3 0L9 12v3z"/>
                </>
              ) : (
                <>
                  <path d="m18 2 3 3"/>
                  <path d="M14.5 5.5l-11 11V20h3.5l11-11z"/>
                </>
              )}
            </svg>
          </button>
          {isEditing ? (
            <input
              ref={inputRef}
              type="text"
              value={fieldLabel}
              onChange={(e) => setFieldLabel(e.target.value)}
              onKeyDown={handleLabelKeyDown}
              className="field-label-input"
            />
          ) : (
            <label htmlFor={inputId} className="field-label">
              {field.label}
              {isRequired && <span className="required-mark">*</span>}
            </label>
          )}
        </div>
        <div className="field-actions">
          <EditFieldButton field={field} onUpdateField={handleUpdateField} />
          <button 
            className="delete-field-button" 
            onClick={() => onDelete(field.id)}
            title="Delete field"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3,6 5,6 21,6"/>
              <path d="m19,6v14a2,2 0,0 1,-2,2H7a2,2 0,0 1,-2,-2V6m3,0V4a2,2 0,0 1,2,-2h4a2,2 0,0 1,2,2v2"/>
              <line x1="10" y1="11" x2="10" y2="17"/>
              <line x1="14" y1="11" x2="14" y2="17"/>
            </svg>
          </button>
        </div>
      </div>
      
      <div className="field-input-container">
        {field.type === 'checkbox' ? (
          <label className="checkbox-label">
            {renderInput()}
            <span>{field.label}</span>
          </label>
        ) : (
          renderInput()
        )}
        {/* Custom file error */}
        {field.type === 'file' && fileError && (
          <div className="field-error" style={{ color: '#dc2626', marginTop: 4 }}>{fileError}</div>
        )}
      </div>
      
      <div className="field-bottom-controls">
        <div className="required-toggle">
          <span className={`required-badge ${isRequired ? 'required' : 'optional'}`}>
            {isRequired ? 'Required' : 'Optional'}
          </span>
          <label className="toggle-switch">
            <input 
              type="checkbox" 
              checked={isRequired} 
              onChange={toggleRequired}
            />
            <span className="slider"></span>
          </label>
        </div>
      </div>
      
      {field.validation && (field.validation.min !== undefined || field.validation.max !== undefined) && (
        <div className="field-validation-info">
          {field.validation.min !== undefined && <span className="validation-badge">Min: {field.validation.min}</span>}
          {field.validation.max !== undefined && <span className="validation-badge">Max: {field.validation.max}</span>}
        </div>
      )}
    </div>
  );
}

FormField.propTypes = {
  field: PropTypes.object.isRequired,
  index: PropTypes.number.isRequired,
  onUpdate: PropTypes.func.isRequired,
  onDelete: PropTypes.func.isRequired
};

export default FormField;
