---
name: springboottest-full-context-instead-of-slice
description: A test annotated with @SpringBootTest takes several seconds per class and starts unrelated beans, when a narrower slice or plain unit test would isolate the real unit faster.
triggers: ["SpringBootTest slow test suite", "test suite takes forever Spring Boot", "full application context loading in test", "which Spring test slice to use"]
permissions: ["READ"]
---

## Symptom
The test suite for a Spring Boot project takes minutes to run even though most tests exercise a single service class's logic. Each `@SpringBootTest`-annotated class prints the full Spring banner and initializes datasources, security filters, and web servers that have nothing to do with the method actually being tested. CI times balloon as the number of `@SpringBootTest` classes grows roughly linearly with total context-startup overhead, not with actual test logic complexity.

## Likely causes
1. **A test only needs to exercise one `@Service` class's business logic with its collaborators mocked, but was scaffolded with `@SpringBootTest` "to be safe"** -- the full application context (every `@Component`, `@Configuration`, datasource, security config) gets built even though the test never touches most of it.
2. **Different test classes use slightly different `@SpringBootTest` configurations** (different `@MockBean`s, different `@ActiveProfiles`, different property overrides), so Spring's test context cache can't reuse a cached context between them -- each class pays full startup cost instead of amortizing it, multiplying the problem across the suite.
3. **A controller test uses `@SpringBootTest` plus manually configured `MockMvc`** instead of `@WebMvcTest`, pulling in the entire service/repository layer when the test only needs the web layer's request mapping, validation, and serialization behavior.
4. **A repository/JPA test uses `@SpringBootTest` instead of `@DataJpaTest`**, starting the full context (web server, security, unrelated services) when only the persistence layer and an embedded/test database are relevant.

## Diagnose
1. Time the suite with `mvn test` and check per-class timings (Surefire reports each test class's duration) or Gradle's `--profile` report -- classes dominated by "before first test" time rather than actual test method time are paying context-startup cost, not test-logic cost.
2. For each slow `@SpringBootTest` class, list what it actually asserts on: does it ever go through an HTTP layer (`MockMvc`, `TestRestTemplate`)? Touch a real/embedded database? Or does it just call one service method and check the return value?
3. Check Spring's context cache behavior by looking for excessive `@DirtiesContext` usage -- that's a strong signal the test is fighting the wrong tool rather than being scoped correctly, since it forces a fresh context per test and defeats caching entirely.
4. Grep the test class for `@MockBean` usage -- if most of the application's beans are being mocked out anyway, that's a strong sign the test doesn't need the container at all and a plain Mockito unit test (or a narrower slice) would do the same job faster.

## Fix
Match the test annotation to the actual layer under test, reserving `@SpringBootTest` for genuine integration tests that need multiple real, wired-together layers:

```java
// Pure business logic with collaborators mocked -- no Spring context at all
@ExtendWith(MockitoExtension.class)
class PricingServiceTest {
    @Mock private DiscountRepository discountRepository;
    @InjectMocks private PricingService pricingService;
}

// Web layer only -- controller, validation, serialization, security filters for this endpoint
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired private MockMvc mockMvc;
    @MockBean private OrderService orderService;
}

// Persistence layer only -- JPA repositories against an embedded/test DB
@DataJpaTest
class OrderRepositoryTest {
    @Autowired private OrderRepository orderRepository;
}
```

The reasoning: a plain Mockito-based unit test (no Spring annotations at all) is the right default for testing a single class's logic -- it needs zero context startup. Reach for a slice annotation (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, etc.) when the test genuinely needs Spring's wiring for one layer. Reserve full `@SpringBootTest` for a small number of true end-to-end integration tests that verify the whole assembly works together.

## Pitfalls
Don't over-correct by converting every test to a slice test if the class under test has almost no Spring-specific behavior to verify (e.g. a `@Service` with no autowired beans at all) -- at that point even a slice annotation is unnecessary overhead, and a plain `MockitoExtension` unit test with no Spring involvement whatsoever is faster and simpler still. Slice tests are a middle ground, not the default target for everything.

## Verify
After converting a test from `@SpringBootTest` to a plain unit test or slice, compare the Surefire/Gradle per-class timing before and after -- confirm the specific class's duration drops from seconds to milliseconds, and confirm the suite's total wall-clock time drops when run across the whole module (`mvn test` end-to-end timing).
