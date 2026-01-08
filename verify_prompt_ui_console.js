// Run this in browser console after page loads to verify prompt UI
(async () => {
    console.log('🔍 Starting UI Verification...');
    
    // 1. Check API
    const apiResponse = await fetch('/api/workflow/config/prompts');
    const apiData = await apiResponse.json();
    const cmdlinePrompt = apiData.prompts?.CmdlineExtract?.prompt || '';
    const parsed = JSON.parse(cmdlinePrompt);
    const expectedSystem = parsed.role || '';
    const expectedUser = parsed.user_template || '';
    
    console.log('📊 API Data:');
    console.log('  Expected System:', expectedSystem);
    console.log('  Expected User:', expectedUser);
    
    // 2. Check UI elements
    const systemDisplay = document.getElementById('cmdlineextract-prompt-system-display-2');
    const userDisplay = document.getElementById('cmdlineextract-prompt-user-display-2');
    
    console.log('📊 UI Elements:');
    console.log('  System element exists:', !!systemDisplay);
    console.log('  User element exists:', !!userDisplay);
    
    if (!systemDisplay || !userDisplay) {
        console.error('❌ Display elements not found!');
        console.log('  System ID: cmdlineextract-prompt-system-display-2');
        console.log('  User ID: cmdlineextract-prompt-user-display-2');
        return;
    }
    
    const actualSystem = systemDisplay.textContent.trim();
    const actualUser = userDisplay.textContent.trim();
    
    console.log('  Actual System:', actualSystem);
    console.log('  Actual User:', actualUser);
    
    // 3. Verify
    console.log('\n🔍 Verification:');
    const systemMatch = actualSystem === expectedSystem;
    const userMatch = actualUser === expectedUser;
    
    console.log('  System matches:', systemMatch);
    console.log('  User matches:', userMatch);
    
    if (systemMatch && userMatch) {
        console.log('\n✅ VERIFICATION PASSED: UI matches API');
    } else {
        console.error('\n❌ VERIFICATION FAILED: UI does not match API');
        if (!systemMatch) {
            console.error('  System mismatch:');
            console.error('    Expected:', expectedSystem);
            console.error('    Actual:', actualSystem);
        }
        if (!userMatch) {
            console.error('  User mismatch:');
            console.error('    Expected:', expectedUser);
            console.error('    Actual:', actualUser);
        }
    }
})();

