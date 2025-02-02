from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Union
import math
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Number Properties API",
    description="API that returns mathematical properties and fun facts about numbers",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def is_prime(n: int) -> bool:
    """Check if a number is prime."""
    if n < 2:
        return False
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return False
    return True


def is_perfect(n: int) -> bool:
    """Check if a number is perfect (sum of proper divisors equals the number)."""
    if n <= 1:
        return False
    divisor_sum = sum(i for i in range(1, n) if n % i == 0)
    return divisor_sum == n


def is_armstrong(n: int) -> bool:
    """Check if a number is an Armstrong number."""
    num_str = str(n)
    power = len(num_str)
    return n == sum(int(digit) ** power for digit in num_str)


def get_number_properties(n: int) -> List[str]:
    """Get a list of properties for a given number."""
    properties = []

    # Basic properties
    if n % 2 == 0:
        properties.append("even")
    else:
        properties.append("odd")

    if is_prime(n):
        properties.append("prime")

    if is_perfect(n):
        properties.append("perfect")

    if is_armstrong(n):
        properties.append("armstrong")

    return properties


def digit_sum(n: int) -> int:
    """Calculate the sum of digits."""
    return sum(int(digit) for digit in str(abs(n)))


def generate_fun_fact(n: int, properties: List[str]) -> str:
    """Generate a fun fact about the number based on its properties."""
    if "armstrong" in properties:
        num_str = str(n)
        power = len(num_str)
        return (
            f"{n} is an Armstrong number because "
            + " + ".join(f"{digit}^{power}" for digit in num_str)
            + f" = {n}"
        )
    elif "perfect" in properties:
        divisors = [str(i) for i in range(1, n) if n % i == 0]
        return (
            f"{n} is a perfect number because "
            + " + ".join(divisors)
            + f" = {n}"
        )
    elif "prime" in properties:
        return f"{n} is a prime number, divisible only by 1 and itself"
    else:
        return f"{n} is a {', '.join(properties)} number"


@app.get("/api/classify-number")
async def classify_number(
    number: str,
) -> Dict[str, Union[int, bool, List[str], str]]:
    """
    Analyze a number and return its mathematical properties.

    Args:
        number: The number to analyze (as string to handle invalid inputs)

    Returns:
        Dictionary containing number properties and fun fact

    Raises:
        HTTPException: If input is invalid
    """
    try:
        num = int(number)
    except ValueError:
        return JSONResponse(
            status_code=400, content={"number": number, "error": True}
        )

    properties = get_number_properties(num)

    return {
        "number": num,
        "is_prime": is_prime(num),
        "is_perfect": is_perfect(num),
        "properties": properties,
        "class_sum": digit_sum(num),
        "fun_fact": generate_fun_fact(num, properties),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
