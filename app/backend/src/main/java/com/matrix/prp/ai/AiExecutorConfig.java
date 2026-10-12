package com.matrix.prp.ai;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class AiExecutorConfig {
    @Bean("aiExecutor")
    public ThreadPoolTaskExecutor aiExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(12);
        pool.setThreadNamePrefix("prp-ai-");
        pool.setWaitForTasksToCompleteOnShutdown(false);
        pool.initialize();
        return pool;
    }
}
