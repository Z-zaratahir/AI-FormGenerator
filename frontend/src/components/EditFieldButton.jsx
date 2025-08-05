import { useState } from 'react';
import PropTypes from 'prop-types';
import FieldTypeSelector from './FieldTypeSelector';
import '../styles/EditFieldButton.css';

/**
 * EditFieldButton Component
 * 
 * A button that opens the field type selector modal to change a field's type
 * 
 * @param {object} field - The current field data 
 * @param {function} onUpdateField - Function to call with the updated field data
 */
function EditFieldButton({ field, onUpdateField }) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleOpenModal = () => {
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
  };

  const handleSelectFieldType = (fieldType) => {
    // Preserve the field's ID and label, but change its type
    const updatedField = {
      ...field,
      type: fieldType,
      // Reset options if switching to/from select or radio
      options: (fieldType === 'select' || fieldType === 'radio') 
        ? (field.options?.length ? field.options : ['Option 1', 'Option 2']) 
        : []
    };
    
    // Call the parent component's handler with the updated field
    onUpdateField(updatedField);
  };

  return (
    <>
      <button className="edit-field-type-button" onClick={handleOpenModal} title="Change field type">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
          <circle cx="9" cy="9" r="2"/>
          <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
        </svg>
      </button>
      
      <FieldTypeSelector 
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        onSelectFieldType={handleSelectFieldType}
        mode="edit"
        currentField={field}
      />
    </>
  );
}

EditFieldButton.propTypes = {
  field: PropTypes.object.isRequired,
  onUpdateField: PropTypes.func.isRequired
};

export default EditFieldButton;
