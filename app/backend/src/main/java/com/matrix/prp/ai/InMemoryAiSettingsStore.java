package com.matrix.prp.ai;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Repository;

@Repository
@Profile("test")
public class InMemoryAiSettingsStore implements AiSettingsStore {
    private final Map<Long, Selection> preferences = new HashMap<>();
    private final Map<Long, Map<String, String>> credentials = new HashMap<>();
    @Override public synchronized Optional<Selection> selection(long user) {
        return Optional.ofNullable(preferences.get(user));
    }
    @Override public synchronized Map<String, String> encryptedKeys(long user) {
        return Map.copyOf(credentials.getOrDefault(user, Map.of()));
    }
    @Override public synchronized void putKey(long user, String provider, String encrypted) {
        credentials.computeIfAbsent(user, k -> new HashMap<>()).put(provider, encrypted);
    }
    @Override public synchronized void deleteKey(long user, String provider) {
        credentials.computeIfAbsent(user, k -> new HashMap<>()).remove(provider);
    }
    @Override public synchronized void select(long user, String provider, String model) {
        preferences.put(user, new Selection(provider, model));
    }
}
