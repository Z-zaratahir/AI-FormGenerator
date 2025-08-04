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
        <span className="edit-icon">✏️</span>
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
