package com.matrix.prp.config;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("!test")
@MapperScan({
        "com.matrix.prp.records.mapper",
        "com.matrix.prp.tasks.mapper",
        "com.matrix.prp.finance.mapper",
        "com.matrix.prp.reviews.mapper",
        "com.matrix.prp.tags.mapper"
})
public class MyBatisConfig {
}
