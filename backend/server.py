from fastapi import FastAPI, APIRouter, HTTPException, Response, Request, Depends
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import httpx
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===================== MODELS =====================

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    interests: List[str] = []
    onboarding_completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Article(BaseModel):
    model_config = ConfigDict(extra="ignore")
    article_id: str = Field(default_factory=lambda: f"article_{uuid.uuid4().hex[:12]}")
    title: str
    description: str
    content: str
    what: str
    why: str
    context: str
    impact: str
    category: str
    subcategory: Optional[str] = None
    image_url: str
    source: str
    author: Optional[str] = None
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_developing: bool = False
    is_breaking: bool = False
    likes: int = 0
    dislikes: int = 0
    view_count: int = 0

class Poll(BaseModel):
    model_config = ConfigDict(extra="ignore")
    poll_id: str = Field(default_factory=lambda: f"poll_{uuid.uuid4().hex[:12]}")
    article_id: str
    question: str
    options: List[str]
    votes: Dict[str, int] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Comment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    comment_id: str = Field(default_factory=lambda: f"comment_{uuid.uuid4().hex[:12]}")
    article_id: str
    user_id: str
    user_name: str
    user_picture: Optional[str] = None
    content: str
    stance: str  # "agree" or "disagree"
    likes: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Bookmark(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bookmark_id: str = Field(default_factory=lambda: f"bookmark_{uuid.uuid4().hex[:12]}")
    user_id: str
    article_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ReadingHistory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    history_id: str = Field(default_factory=lambda: f"history_{uuid.uuid4().hex[:12]}")
    user_id: str
    article_id: str
    time_spent: int = 0  # seconds
    completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    session_id: str
    user_id: str
    article_id: str
    role: str  # "user" or "assistant"
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ===================== REQUEST/RESPONSE MODELS =====================

class InterestsUpdate(BaseModel):
    interests: List[str]

class ArticleInteraction(BaseModel):
    action: str  # "like", "dislike", "view"

class PollVote(BaseModel):
    option: str

class CommentCreate(BaseModel):
    content: str
    stance: str

class AskAIRequest(BaseModel):
    message: str
    article_id: str

class RelevanceFeedback(BaseModel):
    article_id: str
    is_relevant: bool

# ===================== SAMPLE NEWS DATA =====================

SAMPLE_ARTICLES = [
    {
        "article_id": "article_india001",
        "title": "India's Chandrayaan-4 Mission Set to Launch in 2026, ISRO Announces Lunar Sample Return",
        "description": "ISRO confirms ambitious lunar sample return mission, positioning India as fourth nation to achieve this milestone",
        "content": "The Indian Space Research Organisation (ISRO) has officially announced that the Chandrayaan-4 mission is on track for a 2026 launch. This ambitious mission aims to bring back lunar soil samples to Earth, a feat only achieved by the USA, Russia, and China so far. The mission will involve multiple spacecraft working in tandem - an orbiter, lander, ascender, and a transfer module.",
        "what": "ISRO announces Chandrayaan-4 lunar sample return mission scheduled for 2026, involving four spacecraft modules working together.",
        "why": "India seeks to join elite club of nations that have returned lunar samples, advancing scientific research and demonstrating technological prowess.",
        "context": "Following the historic success of Chandrayaan-3's soft landing in 2023, India has accelerated its space ambitions. The global space race has intensified with China's Chang'e missions and NASA's Artemis program.",
        "impact": "Success would establish India as a major space power, boost domestic space industry, attract international collaborations, and provide valuable lunar samples for scientific research.",
        "category": "Science",
        "subcategory": "Space",
        "image_url": "https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?w=800",
        "source": "ISRO Press Release",
        "author": "Science Desk",
        "is_developing": True,
        "is_breaking": False
    },
    {
        "article_id": "article_india002",
        "title": "Union Budget 2026: Finance Minister Proposes ₹15 Lakh Crore Infrastructure Push",
        "description": "Massive capital expenditure plan targets roads, railways, and digital infrastructure across tier-2 and tier-3 cities",
        "content": "In a significant boost to India's infrastructure development, the Finance Minister unveiled a ₹15 lakh crore capital expenditure plan for FY2026-27. The budget prioritizes connectivity in tier-2 and tier-3 cities, with major allocations for highways, dedicated freight corridors, and 5G expansion. The government also announced tax incentives for semiconductor manufacturing units.",
        "what": "Union Budget allocates record ₹15 lakh crore for infrastructure development, focusing on smaller cities and digital connectivity.",
        "why": "To accelerate economic growth, create employment, reduce urban-rural divide, and position India as a global manufacturing hub.",
        "context": "India aims to become a $5 trillion economy. Infrastructure development is crucial for attracting foreign investment and boosting domestic manufacturing under Make in India initiative.",
        "impact": "Expected to create 50 lakh jobs, boost GDP growth by 0.5%, improve logistics efficiency, and accelerate urbanization of tier-2/3 cities.",
        "category": "Business",
        "subcategory": "Economy",
        "image_url": "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?w=800",
        "source": "Ministry of Finance",
        "author": "Economy Bureau",
        "is_developing": False,
        "is_breaking": True
    },
    {
        "article_id": "article_india003",
        "title": "India vs Australia: Rohit Sharma's Men Eye Historic Series Win at Gabba",
        "description": "After dramatic Adelaide victory, Team India enters Brisbane Test with 2-1 series lead",
        "content": "The Indian cricket team arrives at the Gabba with momentum on their side following a thrilling 4-wicket victory in Adelaide. Captain Rohit Sharma's tactical acumen and Jasprit Bumrah's lethal bowling have been instrumental in the series lead. The Gabba, historically a fortress for Australia, witnessed India's breakthrough victory in 2021, and the team aims to recreate that magic.",
        "what": "India leads Border-Gavaskar Trophy 2-1 heading into the crucial Gabba Test, seeking to seal historic series victory.",
        "why": "A series win in Australia would cement India's dominance in Test cricket and continue their remarkable overseas success story.",
        "context": "India's 2021 Gabba triumph remains one of cricket's greatest upsets. Australia hasn't lost a Test series at home since that defeat, making this contest highly anticipated.",
        "impact": "Victory would secure World Test Championship final spot, boost Indian cricket's global standing, and continue Australia's home struggles against India.",
        "category": "Sports",
        "subcategory": "Cricket",
        "image_url": "https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=800",
        "source": "Sports Correspondent",
        "author": "Cricket Desk",
        "is_developing": True,
        "is_breaking": False
    },
    {
        "article_id": "article_india004",
        "title": "Supreme Court Upholds Privacy Rights in Landmark Data Protection Ruling",
        "description": "Verdict strengthens individual rights under Digital Personal Data Protection Act",
        "content": "In a landmark judgment, the Supreme Court of India has reinforced the fundamental right to privacy in the digital age. The five-judge constitutional bench ruled that citizens have absolute right to know how their personal data is being used by both government and private entities. The ruling comes as the Digital Personal Data Protection Act enters its implementation phase.",
        "what": "Supreme Court delivers historic ruling strengthening data privacy rights, mandating transparency from data collectors.",
        "why": "To protect citizens from surveillance overreach and corporate data exploitation in an increasingly digital economy.",
        "context": "The judgment builds on the 2017 Puttaswamy case that recognized privacy as a fundamental right. India's digital population of 800 million makes data protection crucial.",
        "impact": "Tech companies must overhaul data practices, government surveillance faces new constraints, citizens gain stronger legal recourse against data misuse.",
        "category": "Politics",
        "subcategory": "Judiciary",
        "image_url": "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=800",
        "source": "Legal Correspondent",
        "author": "Law Bureau",
        "is_developing": False,
        "is_breaking": True
    },
    {
        "article_id": "article_india005",
        "title": "Bengaluru Startup Develops Indigenous AI Chip, Challenges Global Giants",
        "description": "Homegrown semiconductor company secures $200M funding for AI accelerator manufacturing",
        "content": "A Bengaluru-based startup has achieved a significant breakthrough in developing an indigenous AI accelerator chip that promises to compete with offerings from NVIDIA and AMD. The company has secured $200 million in Series C funding led by global venture capital firms. The chip, designed specifically for edge AI applications, offers 40% better power efficiency than existing solutions.",
        "what": "Indian startup develops indigenous AI chip with superior power efficiency, raises $200M for manufacturing scale-up.",
        "why": "To reduce India's dependence on imported semiconductors and establish presence in the strategic AI hardware market.",
        "context": "Global chip shortage and geopolitical tensions have highlighted the need for semiconductor self-reliance. India's semiconductor mission aims to create a $55 billion industry by 2030.",
        "impact": "Could position India in global AI supply chain, create high-tech jobs, reduce import dependency, and boost national security in critical tech sectors.",
        "category": "Technology",
        "subcategory": "Startups",
        "image_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800",
        "source": "Tech Reporter",
        "author": "Startup Desk",
        "is_developing": True,
        "is_breaking": False
    },
    {
        "article_id": "article_india006",
        "title": "Monsoon Session: Parliament Passes Women's Reservation Bill with 2/3 Majority",
        "description": "Historic legislation guarantees 33% seats for women in Lok Sabha and State Assemblies",
        "content": "In a historic moment for Indian democracy, Parliament has passed the Women's Reservation Bill with overwhelming support from across party lines. The constitutional amendment guarantees 33% reservation for women in the Lok Sabha and all State Legislative Assemblies. The bill, first introduced in 1996, finally becomes law after nearly three decades of debate and deliberation.",
        "what": "Parliament passes Women's Reservation Bill guaranteeing 33% seats for women in legislative bodies with over 2/3 majority.",
        "why": "To address chronic underrepresentation of women in Indian politics and ensure gender-balanced governance.",
        "context": "Women currently hold only 15% of Lok Sabha seats. The bill has been a pending demand since 1996, blocked repeatedly due to political disagreements.",
        "impact": "Will transform Indian political landscape, potentially adding 180+ women MPs, influence policy priorities toward education, health, and social welfare.",
        "category": "Politics",
        "subcategory": "Parliament",
        "image_url": "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?w=800",
        "source": "Parliamentary Bureau",
        "author": "Political Editor",
        "is_developing": False,
        "is_breaking": True
    },
    {
        "article_id": "article_india007",
        "title": "Mumbai Metro Phase 3 Opens: India's Longest Underground Corridor Transforms City Commute",
        "description": "33.5 km underground metro connects Colaba to SEEPZ, expected to serve 2 million daily",
        "content": "Mumbai has inaugurated India's longest underground metro corridor, stretching 33.5 kilometers from Colaba in the south to SEEPZ in the north. The ₹37,000 crore project features 27 stations, including the country's deepest at 32 meters below sea level. Advanced signaling technology allows trains every 3 minutes during peak hours.",
        "what": "Mumbai Metro Phase 3, India's longest underground corridor at 33.5 km with 27 stations, begins commercial operations.",
        "why": "To decongest Mumbai's overburdened suburban railways and roads, reducing commute times by up to 60%.",
        "context": "Mumbai's existing transport infrastructure serves 80 lakh daily commuters under extreme capacity stress. The city has long needed mass rapid transit alternatives.",
        "impact": "Will reduce commute times, decrease road accidents, lower carbon emissions, boost property values along corridor, and set precedent for other cities.",
        "category": "Technology",
        "subcategory": "Infrastructure",
        "image_url": "https://images.unsplash.com/photo-1544620347-c4fd4a3d5957?w=800",
        "source": "Metro Rail Corporation",
        "author": "Infrastructure Desk",
        "is_developing": False,
        "is_breaking": False
    },
    {
        "article_id": "article_india008",
        "title": "Reliance Jio and Starlink Partnership: Satellite Internet to Reach Remote India",
        "description": "Landmark deal aims to provide high-speed internet to 100,000 villages by 2027",
        "content": "Reliance Jio has announced a strategic partnership with SpaceX's Starlink to bring satellite-based internet connectivity to India's most remote regions. The collaboration will deploy low-earth orbit satellite internet in areas where traditional telecom infrastructure is unviable. The first phase targets 100,000 villages across Northeast India, Himachal Pradesh, and island territories.",
        "what": "Jio partners with Starlink to deploy satellite internet across 100,000 remote Indian villages lacking telecom infrastructure.",
        "why": "To bridge India's digital divide, bringing internet access to geographically challenging regions not covered by fiber or cellular networks.",
        "context": "Over 25,000 villages in India still lack any internet connectivity. Satellite internet has emerged as the only viable solution for extremely remote areas.",
        "impact": "Will enable e-governance, telemedicine, online education in remote areas; unlock economic opportunities; strengthen national integration of border regions.",
        "category": "Technology",
        "subcategory": "Telecom",
        "image_url": "https://images.unsplash.com/photo-1516849841032-87cbac4d88f7?w=800",
        "source": "Telecom Correspondent",
        "author": "Tech Bureau",
        "is_developing": True,
        "is_breaking": False
    },
    {
        "article_id": "article_india009",
        "title": "RBI Holds Rates Steady, Signals Cautious Approach Amid Global Uncertainty",
        "description": "Repo rate unchanged at 6.5% for eighth consecutive meeting as inflation concerns ease",
        "content": "The Reserve Bank of India has maintained the repo rate at 6.5% for the eighth consecutive monetary policy meeting. Governor Shaktikanta Das cited stable domestic inflation, which has returned within the 4% target, while highlighting global economic uncertainties including US tariff policies and geopolitical tensions. GDP growth forecast remains at 7.2% for FY26.",
        "what": "RBI keeps repo rate unchanged at 6.5%, maintains accommodative stance while monitoring global economic conditions.",
        "why": "Balanced approach to support growth while ensuring inflation remains within target range amid global uncertainties.",
        "context": "Indian economy shows resilient growth despite global slowdown. Inflation has moderated from peaks of 7%+ to current 4.2%, within RBI's comfort zone.",
        "impact": "Home loan EMIs remain stable, business borrowing costs unchanged, rupee stability supported, foreign investor confidence maintained.",
        "category": "Business",
        "subcategory": "Banking",
        "image_url": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800",
        "source": "RBI Press Release",
        "author": "Banking Editor",
        "is_developing": False,
        "is_breaking": False
    },
    {
        "article_id": "article_india010",
        "title": "Indian Cinema Sweeps International Film Festival: 'The Last Light' Wins Palme d'Or",
        "description": "Director Anurag Kashyap's meditation on partition makes history at Cannes",
        "content": "Indian cinema has achieved its highest international honor as 'The Last Light', directed by Anurag Kashyap, won the prestigious Palme d'Or at the Cannes Film Festival. The film, a poetic exploration of partition memories told through three generations, features breakthrough performances and stunning cinematography. This marks the first Palme d'Or for an Indian production.",
        "what": "Indian film 'The Last Light' wins Cannes Palme d'Or, becoming the first Indian production to receive cinema's highest honor.",
        "why": "Recognition of Indian cinema's artistic evolution and ability to tell universal stories with cultural authenticity.",
        "context": "Indian films have won awards at Cannes before, but never the top prize. This victory comes amid a renaissance in Indian independent cinema.",
        "impact": "Global spotlight on Indian cinema, increased international distribution opportunities, inspiration for independent filmmakers, cultural soft power boost.",
        "category": "Entertainment",
        "subcategory": "Cinema",
        "image_url": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=800",
        "source": "Entertainment Correspondent",
        "author": "Film Desk",
        "is_developing": False,
        "is_breaking": True
    },
    {
        "article_id": "article_india011",
        "title": "Climate Alert: Northern India Faces Unprecedented Heat Wave, Delhi Crosses 48°C",
        "description": "IMD issues red alert across 12 states; schools closed, power grid under stress",
        "content": "Northern India is experiencing an unprecedented heat wave with temperatures breaching 48°C in Delhi NCR. The India Meteorological Department has issued red alerts across 12 states, advising residents to avoid outdoor activities. Power demand has surged 25% above normal, straining the grid. Hospitals report surge in heat stroke cases, prompting government to set up cooling centers.",
        "what": "Extreme heat wave grips North India with temperatures exceeding 48°C; IMD issues red alerts for 12 states.",
        "why": "Climate change-induced extreme weather events becoming more frequent and intense across the subcontinent.",
        "context": "India has witnessed increasingly severe summers over the past decade. Scientific studies link this to global warming and urban heat island effects.",
        "impact": "Public health emergency in affected regions, agricultural losses, power crisis, economic productivity decline, heightened focus on climate action.",
        "category": "Science",
        "subcategory": "Climate",
        "image_url": "https://images.unsplash.com/photo-1504701954957-2010ec3bcec1?w=800",
        "source": "IMD Bulletin",
        "author": "Environment Desk",
        "is_developing": True,
        "is_breaking": True
    },
    {
        "article_id": "article_india012",
        "title": "UPI Crosses 20 Billion Monthly Transactions, India Leads Global Digital Payments",
        "description": "NPCI reports record digital payment volumes as India's fintech ecosystem matures",
        "content": "India's Unified Payments Interface (UPI) has crossed a historic milestone of 20 billion monthly transactions, cementing the country's position as the global leader in real-time digital payments. The achievement represents a 40% year-on-year growth, with transaction value exceeding ₹20 lakh crore. International adoption has expanded with UPI now operational in 15 countries.",
        "what": "UPI achieves 20 billion monthly transactions milestone, with ₹20 lakh crore transaction value and expansion to 15 countries.",
        "why": "Result of India's digital payments infrastructure investment, smartphone penetration, and policy support for cashless economy.",
        "context": "UPI launched in 2016 and has since become the backbone of India's digital economy, far surpassing similar systems in developed nations.",
        "impact": "Financial inclusion for millions, reduced cash handling costs, model for other nations, boost to fintech startups, transparent economic tracking.",
        "category": "Technology",
        "subcategory": "Fintech",
        "image_url": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?w=800",
        "source": "NPCI Report",
        "author": "Fintech Correspondent",
        "is_developing": False,
        "is_breaking": False
    }
]

SAMPLE_POLLS = [
    {
        "poll_id": "poll_001",
        "article_id": "article_india001",
        "question": "Should India prioritize lunar exploration over Mars missions?",
        "options": ["Yes, Moon first", "No, Mars is the future", "Both equally", "Neither, focus on Earth"],
        "votes": {"Yes, Moon first": 234, "No, Mars is the future": 156, "Both equally": 312, "Neither, focus on Earth": 45}
    },
    {
        "poll_id": "poll_002",
        "article_id": "article_india002",
        "question": "What should be the top priority for infrastructure spending?",
        "options": ["Roads & Highways", "Railways", "Digital Infrastructure", "Urban Development"],
        "votes": {"Roads & Highways": 189, "Railways": 267, "Digital Infrastructure": 312, "Urban Development": 198}
    },
    {
        "poll_id": "poll_003",
        "article_id": "article_india003",
        "question": "Will India win the Border-Gavaskar Trophy 2024-25?",
        "options": ["Yes, 3-1 or better", "Yes, 2-1", "Draw 2-2", "No, Australia wins"],
        "votes": {"Yes, 3-1 or better": 445, "Yes, 2-1": 312, "Draw 2-2": 189, "No, Australia wins": 123}
    },
    {
        "poll_id": "poll_004",
        "article_id": "article_india006",
        "question": "Will Women's Reservation significantly improve governance?",
        "options": ["Yes, transformative change", "Somewhat helpful", "Too early to tell", "No significant impact"],
        "votes": {"Yes, transformative change": 534, "Somewhat helpful": 267, "Too early to tell": 189, "No significant impact": 78}
    }
]

INTEREST_CATEGORIES = {
    "Politics": ["Parliament", "Elections", "Judiciary", "International Relations", "State Politics"],
    "Technology": ["AI & ML", "Startups", "Gadgets", "Fintech", "Space Tech", "Telecom"],
    "Business": ["Markets", "Economy", "Startups", "Real Estate", "Banking", "Corporate"],
    "Sports": ["Cricket", "Football", "Tennis", "Olympics", "Kabaddi", "Motorsport"],
    "Entertainment": ["Bollywood", "OTT", "Music", "Television", "Regional Cinema"],
    "Science": ["Space", "Health", "Environment", "Research", "Climate"],
    "World": ["USA", "China", "Europe", "Middle East", "Southeast Asia"],
    "Lifestyle": ["Travel", "Food", "Fashion", "Wellness", "Automobiles"]
}

# ===================== AUTHENTICATION =====================

async def get_session_from_request(request: Request) -> Optional[dict]:
    """Extract and validate session from cookies or header"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]
    
    if not session_token:
        return None
    
    session_doc = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    
    if not session_doc:
        return None
    
    expires_at = session_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    
    return session_doc

async def get_current_user(request: Request) -> Optional[dict]:
    """Get current user from session"""
    session = await get_session_from_request(request)
    if not session:
        return None
    
    user = await db.users.find_one(
        {"user_id": session["user_id"]},
        {"_id": 0}
    )
    return user

async def require_auth(request: Request) -> dict:
    """Dependency that requires authentication"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

# ===================== AUTH ROUTES =====================

@api_router.post("/auth/session")
async def create_session(request: Request, response: Response):
    """Exchange session_id from Emergent OAuth for session_token"""
    body = await request.json()
    session_id = body.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    # Call Emergent OAuth to get user data
    async with httpx.AsyncClient() as client:
        try:
            oauth_response = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id}
            )
            if oauth_response.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid session")
            
            user_data = oauth_response.json()
        except Exception as e:
            logger.error(f"OAuth error: {e}")
            raise HTTPException(status_code=401, detail="Authentication failed")
    
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    session_token = f"st_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    # Check if user exists
    existing_user = await db.users.find_one(
        {"email": user_data["email"]},
        {"_id": 0}
    )
    
    if existing_user:
        user_id = existing_user["user_id"]
        # Update user info
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "name": user_data["name"],
                "picture": user_data.get("picture")
            }}
        )
    else:
        # Create new user
        new_user = {
            "user_id": user_id,
            "email": user_data["email"],
            "name": user_data["name"],
            "picture": user_data.get("picture"),
            "interests": [],
            "onboarding_completed": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(new_user)
    
    # Create session
    session_doc = {
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.user_sessions.insert_one(session_doc)
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60
    )
    
    # Get updated user
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    return {"user": user, "session_token": session_token}

@api_router.get("/auth/me")
async def get_me(request: Request):
    """Get current authenticated user"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout user"""
    session = await get_session_from_request(request)
    if session:
        await db.user_sessions.delete_one({"session_token": session["session_token"]})
    
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out"}

# ===================== USER ROUTES =====================

@api_router.put("/users/interests")
async def update_interests(interests_update: InterestsUpdate, user: dict = Depends(require_auth)):
    """Update user interests"""
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "interests": interests_update.interests,
            "onboarding_completed": True
        }}
    )
    updated_user = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return updated_user

@api_router.get("/users/stats")
async def get_user_stats(user: dict = Depends(require_auth)):
    """Get user reading stats"""
    # Get reading history
    history = await db.reading_history.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(1000)
    
    total_time = sum(h.get("time_spent", 0) for h in history)
    articles_read = len(history)
    completed = sum(1 for h in history if h.get("completed", False))
    
    # Get bookmarks count
    bookmarks_count = await db.bookmarks.count_documents({"user_id": user["user_id"]})
    
    # Get category breakdown
    category_counts = {}
    for h in history:
        article = await db.articles.find_one({"article_id": h["article_id"]}, {"_id": 0})
        if article:
            cat = article.get("category", "Other")
            category_counts[cat] = category_counts.get(cat, 0) + 1
    
    return {
        "total_reading_time": total_time,
        "articles_read": articles_read,
        "articles_completed": completed,
        "bookmarks_count": bookmarks_count,
        "category_breakdown": category_counts
    }

@api_router.get("/users/weekly-report")
async def get_weekly_report(user: dict = Depends(require_auth)):
    """Generate weekly reading report"""
    # Get reading history
    history = await db.reading_history.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).to_list(1000)
    
    total_time = sum(h.get("time_spent", 0) for h in history)
    articles_read = len(history)
    completed = sum(1 for h in history if h.get("completed", False))
    
    # Get bookmarks count
    bookmarks_count = await db.bookmarks.count_documents({"user_id": user["user_id"]})
    
    # Get category breakdown
    category_counts = {}
    for h in history:
        article = await db.articles.find_one({"article_id": h["article_id"]}, {"_id": 0})
        if article:
            cat = article.get("category", "Other")
            category_counts[cat] = category_counts.get(cat, 0) + 1
    
    top_category = max(category_counts.items(), key=lambda x: x[1])[0] if category_counts else None
    total_minutes = total_time // 60
    completion_rate = round((completed / articles_read) * 100) if articles_read > 0 else 0
    
    # Generate personalized summary
    insights = []
    
    if articles_read > 0:
        insights.append(f"You've engaged with {articles_read} articles this week, showing a healthy appetite for staying informed.")
    
    if total_minutes > 30:
        insights.append(f"With {total_minutes} minutes of reading, you're investing quality time in understanding the world around you.")
    elif total_minutes > 0:
        insights.append(f"You've spent {total_minutes} minutes reading. Consider setting aside a few more minutes each day for deeper engagement.")
    
    if top_category:
        insights.append(f"{top_category} has captured most of your attention. This focus helps you build expertise in areas that matter to you.")
    
    if completion_rate > 70:
        insights.append(f"With a {completion_rate}% completion rate, you're reading articles thoroughly rather than just skimming headlines.")
    elif articles_read > 0:
        insights.append(f"Your {completion_rate}% completion rate suggests room for deeper engagement. Try the collapsible sections for better understanding.")
    
    if bookmarks_count > 0:
        insights.append(f"You've saved {bookmarks_count} articles for later, building a personal knowledge library.")
    
    return {
        "summary": "\n\n".join(insights) if insights else "Start reading articles to generate your personalized weekly insights.",
        "stats": {
            "articlesRead": articles_read,
            "minutesSpent": total_minutes,
            "topCategory": top_category or "Not enough data",
            "completionRate": completion_rate
        }
    }

@api_router.get("/interests/categories")
async def get_interest_categories():
    """Get all interest categories with subcategories"""
    return INTEREST_CATEGORIES

# ===================== ARTICLES ROUTES =====================

@api_router.get("/articles")
async def get_articles(
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    developing: Optional[bool] = None,
    limit: int = 20,
    skip: int = 0,
    request: Request = None
):
    """Get articles with optional filters"""
    # First, ensure sample articles exist in DB
    existing_count = await db.articles.count_documents({})
    if existing_count == 0:
        # Insert sample articles
        for article in SAMPLE_ARTICLES:
            article_doc = {**article}
            article_doc["published_at"] = datetime.now(timezone.utc).isoformat()
            await db.articles.insert_one(article_doc)
    
    # Build query
    query = {}
    if category:
        query["category"] = category
    if subcategory:
        query["subcategory"] = subcategory
    if developing is not None:
        query["is_developing"] = developing
    
    # Get user interests for personalization
    user = await get_current_user(request) if request else None
    if user and user.get("interests") and not category:
        # Prioritize user interests
        query["category"] = {"$in": user["interests"]}
    
    articles = await db.articles.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    
    # If no personalized results, return all
    if not articles and user and user.get("interests"):
        articles = await db.articles.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    
    return articles

@api_router.get("/articles/developing")
async def get_developing_stories():
    """Get developing/breaking stories"""
    articles = await db.articles.find(
        {"$or": [{"is_developing": True}, {"is_breaking": True}]},
        {"_id": 0}
    ).limit(10).to_list(10)
    return articles

@api_router.get("/articles/{article_id}")
async def get_article(article_id: str):
    """Get single article"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article

@api_router.post("/articles/{article_id}/interact")
async def interact_with_article(
    article_id: str,
    interaction: ArticleInteraction,
    user: dict = Depends(require_auth)
):
    """Like, dislike, or track view on article"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    if interaction.action == "like":
        await db.articles.update_one(
            {"article_id": article_id},
            {"$inc": {"likes": 1}}
        )
    elif interaction.action == "dislike":
        await db.articles.update_one(
            {"article_id": article_id},
            {"$inc": {"dislikes": 1}}
        )
    elif interaction.action == "view":
        await db.articles.update_one(
            {"article_id": article_id},
            {"$inc": {"view_count": 1}}
        )
        # Track in reading history
        existing_history = await db.reading_history.find_one({
            "user_id": user["user_id"],
            "article_id": article_id
        })
        if not existing_history:
            history_doc = {
                "history_id": f"history_{uuid.uuid4().hex[:12]}",
                "user_id": user["user_id"],
                "article_id": article_id,
                "time_spent": 0,
                "completed": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.reading_history.insert_one(history_doc)
    
    return {"success": True}

@api_router.post("/articles/{article_id}/reading-time")
async def update_reading_time(
    article_id: str,
    request: Request,
    user: dict = Depends(require_auth)
):
    """Update reading time for article"""
    body = await request.json()
    time_spent = body.get("time_spent", 0)
    completed = body.get("completed", False)
    
    await db.reading_history.update_one(
        {"user_id": user["user_id"], "article_id": article_id},
        {
            "$inc": {"time_spent": time_spent},
            "$set": {"completed": completed}
        },
        upsert=True
    )
    return {"success": True}

# ===================== BRIEFS ROUTES =====================

@api_router.get("/briefs/{brief_type}")
async def get_brief(brief_type: str, request: Request = None):
    """Get morning/midday/night brief"""
    if brief_type not in ["morning", "midday", "night"]:
        raise HTTPException(status_code=400, detail="Invalid brief type")
    
    user = await get_current_user(request) if request else None
    
    # Get articles based on brief type and user interests
    query = {}
    if user and user.get("interests"):
        query["category"] = {"$in": user["interests"]}
    
    limit = 5 if brief_type == "morning" else 3 if brief_type == "midday" else 5
    
    articles = await db.articles.find(query, {"_id": 0}).limit(limit).to_list(limit)
    
    # If no personalized results, get top articles
    if not articles:
        articles = await db.articles.find({}, {"_id": 0}).limit(limit).to_list(limit)
    
    brief_info = {
        "morning": {
            "title": "Morning Brief",
            "subtitle": "Start your day informed",
            "reading_time": "5 min read"
        },
        "midday": {
            "title": "Midday Update",
            "subtitle": "Catch up on what's happening",
            "reading_time": "3 min read"
        },
        "night": {
            "title": "Night Summary",
            "subtitle": "Reflect on the day",
            "reading_time": "5 min read"
        }
    }
    
    return {
        "type": brief_type,
        **brief_info[brief_type],
        "articles": articles
    }

# ===================== AI ROUTES =====================

@api_router.post("/ai/ask")
async def ask_ai(ask_request: AskAIRequest, user: dict = Depends(require_auth)):
    """Ask AI about an article"""
    article = await db.articles.find_one({"article_id": ask_request.article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    if not emergent_key:
        raise HTTPException(status_code=500, detail="AI service not configured")
    
    session_id = f"chat_{user['user_id']}_{ask_request.article_id}"
    
    # Get chat history
    history = await db.chat_messages.find(
        {"session_id": session_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(20)
    
    # Build context
    context = f"""You are Chintan AI, an intelligent news analysis assistant. Your role is to help users understand news articles deeply and think critically.

Article Title: {article['title']}
Article Content: {article['content']}
What happened: {article['what']}
Why it matters: {article['why']}
Context: {article['context']}
Impact: {article['impact']}

Be informative, balanced, and encourage critical thinking. Keep responses concise but insightful."""

    try:
        chat = LlmChat(
            api_key=emergent_key,
            session_id=session_id,
            system_message=context
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        
        user_message = UserMessage(text=ask_request.message)
        response = await chat.send_message(user_message)
        
        # Save messages to DB
        user_msg_doc = {
            "message_id": f"msg_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "user_id": user["user_id"],
            "article_id": ask_request.article_id,
            "role": "user",
            "content": ask_request.message,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_messages.insert_one(user_msg_doc)
        
        ai_msg_doc = {
            "message_id": f"msg_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "user_id": user["user_id"],
            "article_id": ask_request.article_id,
            "role": "assistant",
            "content": response,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_messages.insert_one(ai_msg_doc)
        
        return {"response": response, "session_id": session_id}
    
    except Exception as e:
        logger.error(f"AI error: {e}")
        raise HTTPException(status_code=500, detail="AI service error")

@api_router.get("/ai/chat-history/{article_id}")
async def get_chat_history(article_id: str, user: dict = Depends(require_auth)):
    """Get chat history for an article"""
    session_id = f"chat_{user['user_id']}_{article_id}"
    history = await db.chat_messages.find(
        {"session_id": session_id},
        {"_id": 0}
    ).sort("created_at", 1).to_list(50)
    return history

@api_router.get("/ai/other-side/{article_id}")
async def get_other_side(article_id: str, user: dict = Depends(require_auth)):
    """Get alternative perspective on article"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Check cache
    cached = await db.other_side_cache.find_one({"article_id": article_id}, {"_id": 0})
    if cached:
        return {"analysis": cached["analysis"]}
    
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    if not emergent_key:
        raise HTTPException(status_code=500, detail="AI service not configured")
    
    try:
        chat = LlmChat(
            api_key=emergent_key,
            session_id=f"otherside_{article_id}",
            system_message="""You are a thoughtful analyst helping readers see different angles of news stories. Write in a natural, conversational tone as if explaining to a friend. Never use markdown formatting like asterisks, bullet points, or headers. Write in flowing paragraphs. Avoid phrases like 'It's important to note' or 'One must consider'. Just share the insights directly and naturally."""
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        
        prompt = f"""Here's a news story. Share a different perspective on it in a natural, conversational way. Write 3-4 short paragraphs covering:

First paragraph - A different way to look at this story that most people might not consider.
Second paragraph - What critics or skeptics might say about this.
Third paragraph - Important context that the article might be missing.
Fourth paragraph - One or two questions worth thinking about.

Title: {article['title']}
Story: {article['content']}

Remember: No bullet points, no asterisks, no headers. Just natural paragraphs like you're having a coffee conversation. Keep each paragraph to 2-3 sentences max."""

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        # Cache result
        cache_doc = {
            "article_id": article_id,
            "analysis": response,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.other_side_cache.insert_one(cache_doc)
        
        return {"analysis": response}
    
    except Exception as e:
        logger.error(f"AI error: {e}")
        raise HTTPException(status_code=500, detail="AI service error")

@api_router.get("/ai/questions/{article_id}")
async def get_ai_questions(article_id: str):
    """Get AI-generated questions for article"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Check cache
    cached = await db.ai_questions_cache.find_one({"article_id": article_id}, {"_id": 0})
    if cached:
        return {"questions": cached["questions"]}
    
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    if not emergent_key:
        # Return default questions
        return {"questions": [
            f"What are the immediate implications of {article['title'][:50]}...?",
            "How might this affect ordinary citizens?",
            "What historical parallels can you draw?",
            "Who benefits and who loses from this development?",
            "What should we watch for in the coming weeks?"
        ]}
    
    try:
        chat = LlmChat(
            api_key=emergent_key,
            session_id=f"questions_{article_id}",
            system_message="Generate 5 thought-provoking questions that encourage critical thinking about news articles. Questions should be concise and engaging."
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        
        prompt = f"""Generate 5 smart questions for this article that encourage deep thinking:

Title: {article['title']}
Summary: {article['description']}
Impact: {article['impact']}

Return only the 5 questions, one per line, no numbering."""

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        
        questions = [q.strip() for q in response.strip().split('\n') if q.strip()][:5]
        
        # Cache result
        cache_doc = {
            "article_id": article_id,
            "questions": questions,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.ai_questions_cache.insert_one(cache_doc)
        
        return {"questions": questions}
    
    except Exception as e:
        logger.error(f"AI error: {e}")
        return {"questions": [
            "What are the key takeaways from this news?",
            "How might this affect you personally?",
            "What questions does this raise?",
            "What's the broader context?",
            "What happens next?"
        ]}

# ===================== POLLS ROUTES =====================

@api_router.get("/polls/{article_id}")
async def get_poll(article_id: str):
    """Get poll for article"""
    # Check DB first
    poll = await db.polls.find_one({"article_id": article_id}, {"_id": 0})
    
    if not poll:
        # Check sample polls
        for sample_poll in SAMPLE_POLLS:
            if sample_poll["article_id"] == article_id:
                await db.polls.insert_one({**sample_poll})
                return sample_poll
        return None
    
    return poll

@api_router.post("/polls/{poll_id}/vote")
async def vote_poll(poll_id: str, vote: PollVote, user: dict = Depends(require_auth)):
    """Vote on a poll"""
    poll = await db.polls.find_one({"poll_id": poll_id}, {"_id": 0})
    if not poll:
        raise HTTPException(status_code=404, detail="Poll not found")
    
    if vote.option not in poll["options"]:
        raise HTTPException(status_code=400, detail="Invalid option")
    
    # Check if user already voted
    existing_vote = await db.poll_votes.find_one({
        "poll_id": poll_id,
        "user_id": user["user_id"]
    })
    
    if existing_vote:
        raise HTTPException(status_code=400, detail="Already voted")
    
    # Record vote
    vote_doc = {
        "vote_id": f"vote_{uuid.uuid4().hex[:12]}",
        "poll_id": poll_id,
        "user_id": user["user_id"],
        "option": vote.option,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.poll_votes.insert_one(vote_doc)
    
    # Update poll counts
    await db.polls.update_one(
        {"poll_id": poll_id},
        {"$inc": {f"votes.{vote.option}": 1}}
    )
    
    # Get updated poll
    updated_poll = await db.polls.find_one({"poll_id": poll_id}, {"_id": 0})
    return updated_poll

# ===================== COMMENTS ROUTES =====================

@api_router.get("/comments/{article_id}")
async def get_comments(article_id: str, limit: int = 20, skip: int = 0):
    """Get comments for article"""
    comments = await db.comments.find(
        {"article_id": article_id},
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return comments

@api_router.post("/comments/{article_id}")
async def create_comment(
    article_id: str,
    comment_data: CommentCreate,
    user: dict = Depends(require_auth)
):
    """Create a comment"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    comment_doc = {
        "comment_id": f"comment_{uuid.uuid4().hex[:12]}",
        "article_id": article_id,
        "user_id": user["user_id"],
        "user_name": user["name"],
        "user_picture": user.get("picture"),
        "content": comment_data.content,
        "stance": comment_data.stance,
        "likes": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.comments.insert_one(comment_doc)
    
    return {k: v for k, v in comment_doc.items() if k != "_id"}

@api_router.post("/comments/{comment_id}/like")
async def like_comment(comment_id: str, user: dict = Depends(require_auth)):
    """Like a comment"""
    await db.comments.update_one(
        {"comment_id": comment_id},
        {"$inc": {"likes": 1}}
    )
    return {"success": True}

@api_router.post("/comments/{comment_id}/agree")
async def agree_comment(comment_id: str, user: dict = Depends(require_auth)):
    """Agree with a comment"""
    # Check if already reacted
    existing = await db.comment_reactions.find_one({
        "comment_id": comment_id,
        "user_id": user["user_id"]
    })
    if existing:
        return {"success": False, "message": "Already reacted"}
    
    await db.comments.update_one(
        {"comment_id": comment_id},
        {"$inc": {"agrees": 1}}
    )
    await db.comment_reactions.insert_one({
        "comment_id": comment_id,
        "user_id": user["user_id"],
        "reaction": "agree",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"success": True}

@api_router.post("/comments/{comment_id}/disagree")
async def disagree_comment(comment_id: str, user: dict = Depends(require_auth)):
    """Disagree with a comment"""
    # Check if already reacted
    existing = await db.comment_reactions.find_one({
        "comment_id": comment_id,
        "user_id": user["user_id"]
    })
    if existing:
        return {"success": False, "message": "Already reacted"}
    
    await db.comments.update_one(
        {"comment_id": comment_id},
        {"$inc": {"disagrees": 1}}
    )
    await db.comment_reactions.insert_one({
        "comment_id": comment_id,
        "user_id": user["user_id"],
        "reaction": "disagree",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"success": True}

# ===================== BOOKMARKS ROUTES =====================

@api_router.get("/bookmarks")
async def get_bookmarks(user: dict = Depends(require_auth)):
    """Get user bookmarks"""
    bookmarks = await db.bookmarks.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    # Get full article details
    article_ids = [b["article_id"] for b in bookmarks]
    articles = await db.articles.find(
        {"article_id": {"$in": article_ids}},
        {"_id": 0}
    ).to_list(100)
    
    return articles

@api_router.post("/bookmarks/{article_id}")
async def add_bookmark(article_id: str, user: dict = Depends(require_auth)):
    """Add bookmark"""
    article = await db.articles.find_one({"article_id": article_id}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    existing = await db.bookmarks.find_one({
        "user_id": user["user_id"],
        "article_id": article_id
    })
    
    if existing:
        raise HTTPException(status_code=400, detail="Already bookmarked")
    
    bookmark_doc = {
        "bookmark_id": f"bookmark_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "article_id": article_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.bookmarks.insert_one(bookmark_doc)
    
    return {"success": True}

@api_router.delete("/bookmarks/{article_id}")
async def remove_bookmark(article_id: str, user: dict = Depends(require_auth)):
    """Remove bookmark"""
    result = await db.bookmarks.delete_one({
        "user_id": user["user_id"],
        "article_id": article_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    
    return {"success": True}

@api_router.get("/bookmarks/check/{article_id}")
async def check_bookmark(article_id: str, user: dict = Depends(require_auth)):
    """Check if article is bookmarked"""
    existing = await db.bookmarks.find_one({
        "user_id": user["user_id"],
        "article_id": article_id
    })
    return {"bookmarked": existing is not None}

# ===================== RELEVANCE FEEDBACK =====================

@api_router.post("/feedback/relevance")
async def submit_relevance_feedback(
    feedback: RelevanceFeedback,
    user: dict = Depends(require_auth)
):
    """Submit relevance feedback for algorithm training"""
    feedback_doc = {
        "feedback_id": f"feedback_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "article_id": feedback.article_id,
        "is_relevant": feedback.is_relevant,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.relevance_feedback.insert_one(feedback_doc)
    return {"success": True}

# ===================== BASIC ROUTES =====================

@api_router.get("/")
async def root():
    return {"message": "Chintan API - Don't just consume. Contemplate."}

@api_router.get("/health")
async def health():
    return {"status": "healthy"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
