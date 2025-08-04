import { useState } from 'react';
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
  
  const isRequired = field.validation?.required || false;
  
  // Creating a unique ID for accessibility
  const inputId = `${field.id || 'field'}-${index}`;

  const inputProps = {
    id: inputId,
    name: field.id,
    required: isRequired,
    placeholder: field.placeholder || '',
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

  const toggleEditing = () => {
    if (isEditing) {
      // Save changes when exiting edit mode
      handleUpdateField({
        ...field,
        label: fieldLabel
      });
    }
    setIsEditing(!isEditing);
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
        {isEditing ? (
          <input
            type="text"
            value={fieldLabel}
            onChange={(e) => setFieldLabel(e.target.value)}
            className="field-label-input"
            autoFocus
          />
        ) : (
          <label htmlFor={inputId} className="field-label">
            {field.label}
            {isRequired && <span className="required-mark">*</span>}
          </label>
        )}
        <div className="field-actions">
          <EditFieldButton field={field} onUpdateField={handleUpdateField} />
          <button 
            className="edit-label-button" 
            onClick={toggleEditing}
            title={isEditing ? "Save label" : "Edit label"}
          >
            {isEditing ? '💾' : '🔤'}
          </button>
          <button 
            className="delete-field-button" 
            onClick={() => onDelete(field.id)}
            title="Delete field"
          >
            🗑️
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
