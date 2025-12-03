// Verification script for save button functionality
// Run this in browser console on /workflow page

console.log('=== Save Button Verification ===');

// Test 1: Functions exist
const tests = {
    'updateSaveButtonState exists': typeof updateSaveButtonState === 'function',
    'initializeSaveButton exists': typeof initializeSaveButton === 'function',
    'checkForUnsavedChanges exists': typeof checkForUnsavedChanges === 'function',
    'getCurrentFormState exists': typeof getCurrentFormState === 'function',
    'initializeChangeTracking exists': typeof initializeChangeTracking === 'function',
};

// Test 2: Button exists
const button = document.getElementById('save-config-button');
tests['Button element exists'] = button !== null;
tests['Button has correct ID'] = button?.id === 'save-config-button';

// Test 3: Button initial state
if (button) {
    tests['Button starts disabled'] = button.disabled === true;
    tests['Button has disabled class'] = button.classList.contains('opacity-50') || button.style.opacity === '0.5';
}

// Test 4: Form exists
const form = document.getElementById('workflowConfigForm');
tests['Form exists'] = form !== null;

// Test 5: Required fields exist
const requiredFields = ['rankingThreshold', 'junkFilterThreshold', 'similarityThreshold', 'description'];
requiredFields.forEach(field => {
    tests[`Field ${field} exists`] = document.getElementById(field) !== null;
});

// Test 6: Model selects exist
const modelSelects = ['rankagent-model-2', 'rankagent-temperature'];
modelSelects.forEach(select => {
    tests[`Select ${select} exists`] = document.getElementById(select) !== null;
});

// Run updateSaveButtonState if it exists
if (typeof updateSaveButtonState === 'function') {
    try {
        updateSaveButtonState();
        tests['updateSaveButtonState runs without error'] = true;
    } catch (e) {
        tests['updateSaveButtonState runs without error'] = false;
        console.error('Error running updateSaveButtonState:', e);
    }
}

// Print results
console.table(tests);
const passed = Object.values(tests).filter(v => v === true).length;
const total = Object.keys(tests).length;
console.log(`\n✅ Passed: ${passed}/${total}`);

if (passed === total) {
    console.log('✅ All tests passed!');
} else {
    console.log('❌ Some tests failed. Check the table above.');
}

