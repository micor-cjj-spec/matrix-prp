package com.matrix.prp.ai;

import java.util.Map;
import java.util.Optional;

public interface AiSettingsStore {
    record Selection(String provider, String model) {}
    Optional<Selection> selection(long userId);
    Map<String, String> encryptedKeys(long userId);
    void putKey(long userId, String provider, String ciphertext);
    void deleteKey(long userId, String provider);
    void select(long userId, String provider, String model);
}
